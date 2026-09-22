/* Nova v0.2.0: one VisualPose, one RAF, one writer for every transform. */
(function (global) {
  'use strict';

  const svg = document.getElementById('nova');
  const defs = global.NOVA_STATE_DEFS;
  const groups = global.NOVA_STATE_GROUPS;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const finite = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const reducedMotion = Boolean(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const motionScale = reducedMotion ? 0.28 : 1;
  const byId = id => document.getElementById(id);
  const setAttr = (element, name, value) => {
    if (element && element.getAttribute(name) !== value) element.setAttribute(name, value);
  };

  const bodyGroup = byId('body-group');
  const bodyBase = byId('body-base');
  const bodySheen = byId('body-sheen');
  const bodySubsurface = byId('body-subsurface');
  const bodyEnvironment = byId('body-environment');
  const bodyHighlight = byId('body-highlight');
  const bodyRim = byId('body-rim');
  const shadow = byId('contact-shadow');
  const face = byId('face');
  const mouth = byId('mouth');
  const orbitBack = byId('orbit-back');
  const orbitFront = byId('orbit-front');
  const particles = Array.from(document.querySelectorAll('#particles .nova-particle'));
  const statusMark = byId('status-mark');
  const eyes = [byId('eye-left'), byId('eye-right')];
  const pupilEls = eyes.map(eye => eye.querySelector('.nova-pupil'));
  const glintEls = eyes.map(eye => eye.querySelector('.nova-glint'));
  const lidEls = eyes.map(eye => eye.querySelector('.nova-lid'));
  const numericFields = Object.keys(defs.idle).filter(key => typeof defs.idle[key] === 'number');
  const pose = {
    current: Object.assign({}, defs.idle),
    target: Object.assign({}, defs.idle),
    velocity: Object.fromEntries(numericFields.map(key => [key, 0])),
  };
  const springScratch = { value: 0, velocity: 0 };

  // Two authored, same-topology paths create the crown's gentle low double
  // peak. The points are intentionally local to Nova; no avatar path is used.
  const SHAPE_A = [
    [88, 46], [105, 30], [117, 36], [133, 29], [153, 47], [177, 82],
    [182, 126], [165, 167], [132, 191], [98, 192], [64, 173], [42, 125],
  ];
  const SHAPE_B = [
    [84, 49], [103, 34], [116, 31], [134, 34], [156, 43], [180, 78],
    [180, 122], [169, 163], [137, 188], [101, 196], [67, 170], [40, 122],
  ];

  const PRIORITY = Object.freeze({
    idle: 0, humming: 10, happy: 40, curious: 42, playful: 44, excited: 46,
    saved: 72, launched: 72, reply: 72, dragging: 82, dictating: 86, listening: 88,
    writing: 84, sending: 84, loading: 86, thinking: 84, searching: 80, working: 80,
    spawning: 96, waking: 92, sleeping: 92, alerting: 98, error: 99,
    'powering-down': 100,
  });

  let visualState = 'idle';
  let persistentState = 'idle';
  let sequenceTimer = null;
  let sequenceToken = 0;
  let raf = null;
  let lastFrame = 0;
  let lastAccent = '';
  let lastShapeKey = '';
  let lastBodyTransform = '';
  let lastFaceTransform = '';
  let lastOrbitTransform = '';
  let lastShadowTransform = '';
  let lastMouthTransform = '';
  let lastIdle = { lean: 0, lift: 0, glance: 0, orbit: 0 };
  let idleAction = null;
  let idleIndex = 0;
  let nextIdleAt = 0;
  let nextBlinkAt = 0;
  let blinkStarted = 0;
  let lastStrongInteraction = -Infinity;
  let trickImpulse = null;
  let releaseImpulse = null;
  let orbitAngle = -14;
  let ambientTimer = null;
  let gazeReturnTimer = null;
  let gazeReturnToken = 0;
  let renderMetrics = null;
  const idleIntervals = [11.4, 15.8, 9.6, 17.2, 12.7];
  const idleActions = ['glance', 'dip', 'tilt', 'double-glance', 'orbit-flash'];
  const blinkIntervals = [3.8, 5.1, 4.2, 6.0];

  const gaze = {
    active: false,
    targetX: 0,
    targetY: 0,
    x: 0,
    y: 0,
    vx: 0,
    vy: 0,
    input: { x: 110, y: 110, width: 220, height: 220, nx: 0.5, ny: 0.5, active: false },
  };

  function integrate(value, velocity, target, dt, stiffness, damping, maxVelocity) {
    const force = (target - value) * stiffness;
    let nextVelocity = (velocity + force * dt) * Math.exp(-damping * dt);
    nextVelocity = clamp(nextVelocity, -maxVelocity, maxVelocity);
    let nextValue = value + nextVelocity * dt;
    if (Math.abs(target - nextValue) < 0.0005 && Math.abs(nextVelocity) < 0.002) {
      nextValue = target;
      nextVelocity = 0;
    }
    springScratch.value = nextValue;
    springScratch.velocity = nextVelocity;
  }

  function integratePose(dt) {
    for (const key of numericFields) {
      const stiffness = key === 'orbitSpeed' ? 30 : key === 'pulse' ? 54 : 46;
      const maxVelocity = key.includes('Scale') ? 3 : key === 'bodyLift' ? 26 : 8;
      integrate(pose.current[key], pose.velocity[key], pose.target[key], dt, stiffness, 13, maxVelocity);
      pose.current[key] = springScratch.value;
      pose.velocity[key] = springScratch.velocity;
    }
    integrate(gaze.x, gaze.vx, gaze.targetX, dt, 82, 18, 7.5);
    gaze.x = springScratch.value;
    gaze.vx = springScratch.velocity;
    integrate(gaze.y, gaze.vy, gaze.targetY, dt, 82, 18, 7.5);
    gaze.y = springScratch.value;
    gaze.x = clamp(gaze.x, -1, 1);
    gaze.y = clamp(gaze.y, -1, 1);
  }

  function scheduleNextIdle(now) {
    nextIdleAt = now + idleIntervals[idleIndex % idleIntervals.length] * 1000;
  }

  function scheduleNextBlink(now) {
    nextBlinkAt = now + blinkIntervals[(idleIndex + 1) % blinkIntervals.length] * 1000;
  }

  function updateIdle(now) {
    const ambient = ['idle', 'humming', 'bored', 'drowsy'].includes(visualState);
    lastIdle = { lean: 0, lift: 0, glance: 0, orbit: 0 };
    if (!ambient || sequenceTimer || now - lastStrongInteraction < 30000) {
      idleAction = null;
      return lastIdle;
    }
    if (!nextIdleAt) scheduleNextIdle(now);
    if (!idleAction && now >= nextIdleAt) {
      idleAction = { kind: idleActions[idleIndex % idleActions.length], started: now };
      idleIndex += 1;
      scheduleNextIdle(now);
    }
    if (!idleAction) return lastIdle;
    const elapsed = now - idleAction.started;
    const duration = idleAction.kind === 'orbit-flash' ? 900 : idleAction.kind === 'double-glance' ? 1200 : 1050;
    if (elapsed >= duration) {
      idleAction = null;
      return lastIdle;
    }
    const u = clamp(elapsed / duration, 0, 1);
    const wave = Math.sin(Math.PI * u) * motionScale;
    if (idleAction.kind === 'glance') {
      lastIdle.lean = 2.2 * wave;
      lastIdle.glance = 0.34 * wave;
    } else if (idleAction.kind === 'dip') {
      lastIdle.lift = -2.7 * wave;
    } else if (idleAction.kind === 'tilt') {
      lastIdle.lean = -2.7 * wave;
      lastIdle.lift = 1.2 * wave;
      lastIdle.glance = -0.2 * wave;
    } else if (idleAction.kind === 'double-glance') {
      const doubleWave = Math.sin(u * Math.PI * 4) * wave;
      lastIdle.lean = 1.8 * doubleWave;
      lastIdle.glance = 0.24 * doubleWave;
    } else {
      lastIdle.orbit = wave;
    }
    return lastIdle;
  }

  function updateBlink(now) {
    if (['sleeping', 'spawning', 'powering-down'].includes(visualState)) return 1;
    if (!nextBlinkAt) scheduleNextBlink(now);
    const duration = reducedMotion ? 210 : 145;
    if (!blinkStarted && now >= nextBlinkAt) {
      blinkStarted = now;
      scheduleNextBlink(now);
    }
    if (!blinkStarted) return 1;
    const elapsed = now - blinkStarted;
    if (elapsed >= duration) {
      blinkStarted = 0;
      return 1;
    }
    return clamp(Math.abs((elapsed / duration) * 2 - 1) * 1.2, 0.06, 1);
  }

  function markInteraction(strength = 1) {
    if (strength > 0.15) lastStrongInteraction = performance.now();
    idleAction = null;
  }

  function clearSequence() {
    sequenceToken += 1;
    if (sequenceTimer) clearTimeout(sequenceTimer);
    sequenceTimer = null;
  }

  function setTargets(name) {
    const next = defs[name] || defs.idle;
    for (const key of numericFields) pose.target[key] = finite(next[key], pose.target[key]);
    pose.target.bodyTint = next.bodyTint || defs.idle.bodyTint;
    pose.target.accent = next.accent || defs.idle.accent;
    visualState = defs[name] ? name : 'idle';
  }

  function pointsForMorph(morph) {
    const normalized = clamp(morph, -1, 1);
    return SHAPE_A.map((point, index) => {
      const other = SHAPE_B[index];
      return [
        point[0] + (other[0] - point[0]) * normalized,
        point[1] + (other[1] - point[1]) * normalized,
      ];
    });
  }

  function blobPath(points) {
    const tension = 0.92;
    let path = `M${points[0][0].toFixed(2)} ${points[0][1].toFixed(2)}`;
    for (let index = 0; index < points.length; index += 1) {
      const p0 = points[(index - 1 + points.length) % points.length];
      const p1 = points[index];
      const p2 = points[(index + 1) % points.length];
      const p3 = points[(index + 2) % points.length];
      const c1x = p1[0] + (p2[0] - p0[0]) * tension / 6;
      const c1y = p1[1] + (p2[1] - p0[1]) * tension / 6;
      const c2x = p2[0] - (p3[0] - p1[0]) * tension / 6;
      const c2y = p2[1] - (p3[1] - p1[1]) * tension / 6;
      path += ` C${c1x.toFixed(2)} ${c1y.toFixed(2)} ${c2x.toFixed(2)} ${c2y.toFixed(2)} ${p2[0].toFixed(2)} ${p2[1].toFixed(2)}`;
    }
    return `${path} Z`;
  }

  function impulseValues(now) {
    const result = { lift: 0, scaleX: 0, scaleY: 0, rotation: 0, sparkle: 0 };
    for (const impulse of [trickImpulse, releaseImpulse]) {
      if (!impulse) continue;
      const age = now - impulse.started;
      if (age >= impulse.duration) continue;
      const u = clamp(age / impulse.duration, 0, 1);
      const envelope = Math.sin(Math.PI * u) * impulse.strength * motionScale;
      if (impulse.kind === 'bounce') {
        result.lift += (8 + 17 * impulse.strength) * envelope;
        result.scaleY += 0.06 * envelope;
        result.scaleX -= 0.028 * envelope;
      } else if (impulse.kind === 'sway') {
        result.rotation += Math.sin(Math.PI * 2 * u) * (1.2 + 4.6 * impulse.strength) * (1 - 0.3 * u) * motionScale;
        result.scaleX += 0.024 * envelope;
      } else if (impulse.kind === 'spin') {
        result.rotation += Math.sin(Math.PI * u) * 8 * impulse.strength * motionScale;
      } else if (impulse.kind === 'burst') {
        result.lift += 4.5 * envelope;
        result.sparkle += envelope;
      }
    }
    return result;
  }

  function render(now, dt) {
    integratePose(dt);
    const current = pose.current;
    const idle = updateIdle(now);
    const blink = updateBlink(now);
    const impulse = impulseValues(now);
    const animatedPulse = current.pulse > 0 ? (0.5 + 0.5 * Math.sin(now / 240)) * current.pulse : 0;
    const lift = current.bodyLift + idle.lift + impulse.lift;
    const rotation = current.bodyRotation + idle.lean + impulse.rotation + gaze.x * 1.65 + gaze.y * 0.8;
    const scaleX = current.bodyScaleX * (1 + impulse.scaleX + Math.abs(gaze.x) * 0.008);
    const scaleY = current.bodyScaleY * (1 + impulse.scaleY + Math.abs(gaze.y) * 0.006);
    const bodyTransform = `translate(0 ${(-lift).toFixed(2)}) translate(110 110) rotate(${rotation.toFixed(2)}) skewX(${current.bodySkew.toFixed(2)}) scale(${scaleX.toFixed(4)} ${scaleY.toFixed(4)}) translate(-110 -110)`;
    if (bodyTransform !== lastBodyTransform) {
      setAttr(bodyGroup, 'transform', bodyTransform);
      lastBodyTransform = bodyTransform;
    }

    const shapeKey = current.morph.toFixed(3);
    if (shapeKey !== lastShapeKey) {
      const path = blobPath(pointsForMorph(current.morph));
      setAttr(bodyBase, 'd', path);
      setAttr(bodySheen, 'd', path);
      setAttr(bodyRim, 'd', path);
      lastShapeKey = shapeKey;
    }

    const influence = clamp(current.gazeInfluence, 0, 1);
    const scan = ['searching', 'radar'].includes(visualState) ? Math.sin(now / 260) * 0.16 : 0;
    const gx = clamp((gaze.x + scan) * influence + idle.glance, -1, 1);
    const gy = clamp(gaze.y * influence - current.focus * 0.08, -1, 1);
    const faceTransform = `translate(${(gx * 3.8).toFixed(2)} ${(gy * 2.6).toFixed(2)}) rotate(${(gx * 1.25 + gy * 0.55).toFixed(2)})`;
    if (faceTransform !== lastFaceTransform) {
      setAttr(face, 'transform', faceTransform);
      lastFaceTransform = faceTransform;
    }

    const faceY = 101 + current.faceOffsetY;
    const eyeSx = current.eyeScaleX * (1 + Math.abs(gx) * 0.018);
    const eyeSy = current.eyeScaleY;
    const eyePositions = [
      { x: 77 + gx * 7.2, y: faceY + gy * 14.0, angle: -gx * 1.8 + gy * 0.5 },
      { x: 133 + gx * 8.0, y: faceY + gy * 13.2, angle: -gx * 1.35 + gy * 0.5 },
    ];
    eyePositions.forEach((position, index) => {
      const open = (index === 0 ? current.eyeOpenL : current.eyeOpenR) * blink;
      const sy = eyeSy * clamp(open, 0.05, 1.24);
      setAttr(eyes[index], 'transform', `translate(${position.x.toFixed(2)} ${position.y.toFixed(2)}) rotate(${position.angle.toFixed(2)}) scale(${eyeSx.toFixed(4)} ${sy.toFixed(4)})`);
      const pupilX = clamp(gx * 6.2 + (index === 0 ? gx * 0.28 : gx * 0.62), -7.1, 7.1);
      const pupilY = clamp(gy * 5.6 - current.focus * 1.25, -6.5, 6.5);
      const pupilScale = clamp(0.82 + current.pupilFocus * 0.25, 0.74, 1.12);
      setAttr(pupilEls[index], 'transform', `translate(${pupilX.toFixed(2)} ${pupilY.toFixed(2)}) scale(${pupilScale.toFixed(3)})`);
      setAttr(glintEls[index], 'transform', `translate(${(pupilX - 1.55).toFixed(2)} ${(pupilY - 2).toFixed(2)})`);
      lidEls[index].style.opacity = clamp(0.14 + (1 - open) * 0.38, 0.12, 0.7).toFixed(3);
    });

    const mouthTransform = `translate(110 ${(136 + current.faceOffsetY + gy * 2.2).toFixed(2)}) scale(${(1 + current.mouth * 0.12).toFixed(3)} ${(1 + current.mouth * 0.18).toFixed(3)})`;
    if (mouthTransform !== lastMouthTransform) {
      setAttr(mouth, 'transform', mouthTransform);
      lastMouthTransform = mouthTransform;
    }
    mouth.style.opacity = clamp(current.mouth * (0.64 + animatedPulse * 0.28), 0, 0.9).toFixed(3);

    const accent = pose.target.accent || '#9a886f';
    if (accent !== lastAccent) {
      svg.style.setProperty('--nova-accent', accent);
      lastAccent = accent;
    }
    bodyRim.style.opacity = clamp(current.rimIntensity * (0.82 + animatedPulse * 0.28), 0, 0.78).toFixed(3);
    bodySheen.style.opacity = clamp(0.5 + current.glow * 0.46 + animatedPulse * 0.1, 0.35, 0.9).toFixed(3);
    bodyHighlight.style.opacity = clamp(0.42 + current.glow * 0.38, 0.3, 0.8).toFixed(3);
    bodySubsurface.style.opacity = clamp(current.subsurface + Math.abs(gaze.y) * 0.04, 0.28, 0.9).toFixed(3);
    bodyEnvironment.style.opacity = clamp(0.06 + current.subsurface * 0.06, 0.05, 0.14).toFixed(3);

    setAttr(shadow, 'transform', `translate(0 ${(-lift * 0.12).toFixed(2)}) scale(${(current.shadowScale * (1 - impulse.lift * 0.006)).toFixed(4)} 1)`);
    shadow.style.opacity = clamp(current.shadowOpacity * (1 - Math.max(0, lift) * 0.018), 0.08, 0.32).toFixed(3);
    orbitAngle += current.orbitSpeed * dt * 54;
    const orbitTransform = `rotate(${(current.orbitTilt + orbitAngle + idle.orbit * 5).toFixed(2)} 110 111)`;
    if (orbitTransform !== lastOrbitTransform) {
      setAttr(orbitBack, 'transform', orbitTransform);
      setAttr(orbitFront, 'transform', orbitTransform);
      lastOrbitTransform = orbitTransform;
    }
    orbitBack.style.opacity = clamp(current.orbitOpacity * 0.36, 0, 0.36).toFixed(3);
    orbitFront.style.opacity = clamp(current.orbitOpacity * (0.64 + animatedPulse * 0.22), 0, 0.78).toFixed(3);
    const particleAlpha = clamp(current.particleRate * (0.72 + impulse.sparkle * 0.8), 0, 0.68);
    particles.forEach((particle, index) => {
      const phase = now / (760 + index * 95) + index * 0.71;
      const driftX = Math.sin(phase) * (1.5 + current.particleLife * 2);
      const driftY = Math.cos(phase * 0.82) * (1.5 + current.particleLife * 2);
      setAttr(particle, 'transform', `translate(${driftX.toFixed(2)} ${driftY.toFixed(2)})`);
      particle.style.opacity = (particleAlpha * (0.45 + 0.55 * (0.5 + 0.5 * Math.sin(phase * 1.7)))).toFixed(3);
    });
    statusMark.style.opacity = clamp(current.warning * (0.35 + 0.45 * (0.5 + 0.5 * Math.sin(now / 180))) + current.sparkle * 0.14 + impulse.sparkle * 0.22, 0, 0.72).toFixed(3);

    const rect = svg.getBoundingClientRect();
    const width = rect.width || 220;
    const height = rect.height || 220;
    const scalePageX = width / 220;
    const scalePageY = height / 220;
    const bodyWidth = 140 * Math.abs(scaleX) * scalePageX;
    const bodyHeight = 164 * Math.abs(scaleY) * scalePageY;
    renderMetrics = {
      rect: { x: rect.x, y: rect.y, width, height },
      body: {
        x: rect.x + (110 + idle.lean) * scalePageX - bodyWidth / 2,
        y: rect.y + (29 - lift) * scalePageY,
        width: bodyWidth,
        height: bodyHeight,
      },
      gx,
      gy,
      eyePositions,
      open: [current.eyeOpenL, current.eyeOpenR],
      blink,
      sx: eyeSx,
      sy: eyeSy,
      pupilX: clamp(gx * 6.2, -7.1, 7.1),
      pupilY: clamp(gy * 5.6 - current.focus * 1.25, -6.5, 6.5),
      pupilScale: clamp(0.82 + current.pupilFocus * 0.25, 0.74, 1.12),
      bodyTransform,
    };
  }

  function frame(now) {
    raf = null;
    if (document.hidden) return;
    if (!lastFrame) lastFrame = now;
    const dt = clamp((now - lastFrame) / 1000, 0, 0.05);
    lastFrame = now;
    render(now, dt);
    raf = requestAnimationFrame(frame);
  }

  function clearAmbientTimer() {
    if (ambientTimer) clearTimeout(ambientTimer);
    ambientTimer = null;
  }

  function start() {
    clearAmbientTimer();
    if (document.hidden || raf) return;
    lastFrame = 0;
    raf = requestAnimationFrame(frame);
  }

  function stop() {
    clearAmbientTimer();
    if (raf) cancelAnimationFrame(raf);
    raf = null;
    lastFrame = 0;
  }

  function runTrick(kind, strength = 1) {
    const safeKind = ['bounce', 'sway', 'spin', 'burst'].includes(kind) ? kind : '';
    if (!safeKind) return;
    const safeStrength = clamp(finite(strength, 1), 0, 1);
    trickImpulse = {
      kind: safeKind,
      strength: safeStrength,
      started: performance.now(),
      duration: safeKind === 'burst' ? 720 : 900,
    };
    markInteraction(safeStrength);
    start();
  }

  function setState(name) {
    const safeName = defs[name] ? name : 'idle';
    persistentState = safeName;
    clearSequence();
    setTargets(safeName);
    markInteraction(0.2);
    start();
  }

  function sequence(steps) {
    const list = Array.isArray(steps) ? steps.filter(step => step && defs[step.state]) : [];
    clearSequence();
    const token = ++sequenceToken;
    let index = 0;
    function next() {
      if (token !== sequenceToken) return;
      if (index >= list.length) {
        sequenceTimer = null;
        setTargets(persistentState);
        start();
        return;
      }
      const step = list[index++];
      setTargets(step.state);
      markInteraction(0.18);
      runTrick(step.trick || '', step.strength == null ? 1 : step.strength);
      const duration = clamp(finite(step.ms, 900), 1, 30000);
      sequenceTimer = setTimeout(next, duration);
      start();
    }
    next();
  }

  function enter(source = 'desktop', context = null) {
    // `source` and `context` intentionally remain data-only extension points
    // for a future robot handoff. Desktop uses the same choreography.
    void source;
    void context;
    sequence([
      { state: 'spawning', ms: 520, trick: 'burst', strength: 0.68 },
      { state: 'waking', ms: 760 },
      { state: 'idle', ms: 520 },
    ]);
  }

  function setGaze(x, y, width, height) {
    const viewWidth = finite(width, svg.clientWidth || 220) || 220;
    const viewHeight = finite(height, svg.clientHeight || 220) || 220;
    const nx = clamp(finite(x, viewWidth / 2) / viewWidth, 0, 1);
    const ny = clamp(finite(y, viewHeight / 2) / viewHeight, 0, 1);
    let tx = nx * 2 - 1;
    let ty = ny * 2 - 1;
    const radius = Math.sqrt(tx * tx + ty * ty);
    if (radius > 1) {
      tx /= radius;
      ty /= radius;
    }
    gaze.targetX = tx;
    gaze.targetY = ty;
    gaze.active = true;
    gaze.input = { x: finite(x), y: finite(y), width: viewWidth, height: viewHeight, nx, ny, active: true };
    if (gazeReturnTimer) {
      clearTimeout(gazeReturnTimer);
      gazeReturnTimer = null;
    }
    start();
  }

  function clearGaze() {
    gaze.targetX = 0;
    gaze.targetY = 0;
    gaze.active = false;
    gaze.input = { x: gaze.input.width / 2, y: gaze.input.height / 2, width: gaze.input.width, height: gaze.input.height, nx: 0.5, ny: 0.5, active: false };
    const token = ++gazeReturnToken;
    if (gazeReturnTimer) clearTimeout(gazeReturnTimer);
    gazeReturnTimer = setTimeout(() => {
      if (token === gazeReturnToken) gazeReturnTimer = null;
    }, 460);
    start();
  }

  function dragRelease(kind, strength) {
    if (!['bounce', 'sway'].includes(kind)) return;
    releaseImpulse = {
      kind,
      strength: clamp(finite(strength), 0, 1),
      started: performance.now(),
      duration: kind === 'bounce' ? 820 : 900,
    };
    markInteraction(releaseImpulse.strength);
    start();
  }

  function snapshot() {
    return {
      state: visualState,
      mode: sequenceTimer ? 'sequence' : 'hold',
      persistentState,
      sequenceActive: Boolean(sequenceTimer),
      reducedMotion,
      diagnostics: {
        rafActive: Boolean(raf),
        ambientTimerActive: Boolean(ambientTimer),
        sequenceTimerActive: Boolean(sequenceTimer),
        gazeReturnTimerActive: Boolean(gazeReturnTimer),
        sceneCacheEntries: 0,
      },
    };
  }

  function gazeSnapshot() {
    return {
      target: { x: gaze.targetX, y: gaze.targetY },
      pointer: { x: gaze.x, y: gaze.y },
      input: Object.assign({}, gaze.input),
      pose: { turn: pose.current.bodyRotation + gaze.x * 1.65, tilt: gaze.y * 2.6, roll: pose.current.bodySkew },
    };
  }

  function renderSnapshot() {
    if (!renderMetrics) {
      render(0, 0);
      renderMetrics = renderMetrics || { rect: { x: 0, y: 0, width: 220, height: 220 }, body: { x: 40, y: 29, width: 140, height: 164 }, gx: 0, gy: 0, eyePositions: [{ x: 77, y: 101 }, { x: 133, y: 101 }], open: [1, 1], blink: 1, sx: 1, sy: 1, pupilX: 0, pupilY: 0, pupilScale: 0.92, bodyTransform: '' };
    }
    const metrics = renderMetrics;
    const scaleX = metrics.rect.width / 220;
    const scaleY = metrics.rect.height / 220;
    const eyesSnapshot = metrics.eyePositions.map((position, index) => {
      const open = metrics.open[index] * metrics.blink;
      const eyeScaleY = metrics.sy * clamp(open, 0.05, 1.24);
      const eyeWidth = 44 * metrics.sx * scaleX;
      const eyeHeight = 28 * eyeScaleY * scaleY;
      const pupilX = clamp(metrics.gx * 6.2 + (index === 0 ? metrics.gx * 0.28 : metrics.gx * 0.62), -7.1, 7.1);
      const pupilY = metrics.pupilY;
      return {
        x: metrics.rect.x + position.x * scaleX - eyeWidth / 2,
        y: metrics.rect.y + position.y * scaleY - eyeHeight / 2,
        width: eyeWidth,
        height: eyeHeight,
        transform: `translate(${position.x.toFixed(2)} ${position.y.toFixed(2)}) rotate(${(position.angle || 0).toFixed(2)}) scale(${metrics.sx.toFixed(4)} ${eyeScaleY.toFixed(4)})`,
        pupil: `translate(${pupilX.toFixed(2)} ${pupilY.toFixed(2)}) scale(${metrics.pupilScale.toFixed(3)})`,
      };
    });
    return {
      target: { x: gaze.targetX, y: gaze.targetY },
      pointer: { x: gaze.x, y: gaze.y },
      input: Object.assign({}, gaze.input),
      pose: { turn: pose.current.bodyRotation + gaze.x * 1.65, tilt: gaze.y * 2.6, roll: pose.current.bodySkew },
      svg: metrics.rect,
      groupTransform: metrics.bodyTransform,
      bodyPath: blobPath(pointsForMorph(pose.current.morph)),
      body: metrics.body,
      eyes: eyesSnapshot,
    };
  }

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stop();
    else start();
  });

  setTargets('idle');
  global.NovaRenderer = Object.freeze({
    setState,
    sequence,
    react: (state, trick = '', duration = 2600) => sequence([{ state, trick, ms: duration }]),
    enter,
    handoff_enter: enter,
    gaze: setGaze,
    clearGaze,
    dragRelease,
    snapshot,
    states: () => groups,
    gazeSnapshot,
    renderSnapshot,
    start,
    stop,
  });
  start();
})(window);
