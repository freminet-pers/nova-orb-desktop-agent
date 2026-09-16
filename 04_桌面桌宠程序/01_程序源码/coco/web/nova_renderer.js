/* Deterministic, offline Nova Orb renderer. State code sets targets; this
 * module is the sole writer of the SVG pose each frame. */
(function (global) {
  'use strict';

  const svg = document.getElementById('nova');
  const defs = global.NOVA_STATE_DEFS;
  const groups = global.NOVA_STATE_GROUPS;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const finite = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const motionScale = reducedMotion ? 0.28 : 1;
  svg.dataset.reducedMotion = reducedMotion ? 'true' : 'false';

  const numericFields = Object.keys(defs.idle).filter(key => typeof defs.idle[key] === 'number');
  const pose = {
    current: Object.assign({}, defs.idle),
    target: Object.assign({}, defs.idle),
    velocity: Object.fromEntries(numericFields.map(key => [key, 0])),
  };

  const bodyGroup = document.getElementById('body-group');
  const face = document.getElementById('face');
  const particles = Array.from(document.querySelectorAll('#particles .nova-particle'));
  const eyes = [document.getElementById('eye-left'), document.getElementById('eye-right')];
  const pupilEls = eyes.map(eye => eye.querySelector('.nova-pupil'));
  const glintEls = eyes.map(eye => Array.from(eye.querySelectorAll('.nova-glint')));
  const lidEls = eyes.map(eye => eye.querySelector('.nova-lid'));
  const canvas = document.getElementById('nova-canvas');
  const canvasContext = canvas && canvas.getContext('2d');
  let canvasScaleX = 1;
  let canvasScaleY = 1;
  let lastGroupTransform = '';
  let lastSnapshotGroupTransform = '';
  let lastFaceTransform = '';
  let lastFaceExpressionKey = '';
  let lastSvgState = '';
  let cachedCanvasGradients = null;
  const sceneCache = new Map();
  const SCENE_CACHE_LIMIT = 12;

  // Twelve authored control points keep the base contour asymmetric while the
  // second point set supplies a bounded expression morph. No source shape is
  // imported from an avatar, icon pack, or remote library.
  const SHAPE_A = [
    [110, 28], [141, 32], [177, 58], [191, 91], [185, 128], [169, 176],
    [139, 195], [105, 199], [72, 188], [45, 161], [34, 123], [38, 82],
  ];
  const SHAPE_B = [
    [108, 32], [137, 29], [174, 49], [194, 82], [181, 119], [178, 158],
    [151, 190], [116, 202], [80, 193], [51, 174], [31, 137], [42, 79],
  ];

  let visualState = 'idle';
  let persistentState = 'idle';
  let sequenceTimer = null;
  let sequenceToken = 0;
  let raf = null;
  let lastFrame = 0;
  let lastPaint = -Infinity;
  let paintRequested = true;
  let lastIdle = { lean: 0, lift: 0, glance: 0, orbit: 0 };
  let lastBlink = 1;
  let orbitAngle = -18;
  let idleAction = null;
  let idleIndex = 0;
  let nextIdleAt = 0;
  let lastStrongInteraction = -Infinity;
  let nextBlinkAt = 0;
  let blinkUntil = 0;
  let trickImpulse = null;
  let releaseImpulse = null;
  let springNextValue = 0;
  let springNextVelocity = 0;
  const idleResult = { lean: 0, lift: 0, glance: 0, orbit: 0 };
  let shapePathKey = '';
  let highlightPathKey = '';
  let shapePath = '';
  let highlightPath = '';
  let paintedCacheKey = '';
  let gazeReturnTimer = null;
  let gazeReturnToken = 0;
  let ambientTimer = null;
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

  function spring(value, velocity, target, dt, stiffness = 48, damping = 13, maxVelocity = 8) {
    const force = (target - value) * stiffness;
    let nextVelocity = (velocity + force * dt) * Math.exp(-damping * dt);
    nextVelocity = clamp(nextVelocity, -maxVelocity, maxVelocity);
    let nextValue = value + nextVelocity * dt;
    if (Math.abs(target - nextValue) < 0.0005 && Math.abs(nextVelocity) < 0.002) {
      nextValue = target;
      nextVelocity = 0;
    }
    // Reuse scalar scratch slots; returning a fresh array for every field on
    // every RAF tick makes the embedded Chromium heap retain needless churn.
    springNextValue = nextValue;
    springNextVelocity = nextVelocity;
  }

  function interpolatePose(dt) {
    for (const key of numericFields) {
      const stiffness = key === 'orbitSpeed' ? 32 : key === 'pulse' ? 58 : 48;
      const maxVelocity = key.includes('Scale') ? 3 : key === 'bodyLift' ? 28 : 8;
      spring(pose.current[key], pose.velocity[key], pose.target[key], dt, stiffness, 13, maxVelocity);
      pose.current[key] = springNextValue;
      pose.velocity[key] = springNextVelocity;
    }
    spring(gaze.x, gaze.vx, gaze.targetX, dt, 64, 17, 7);
    gaze.x = springNextValue; gaze.vx = springNextVelocity;
    spring(gaze.y, gaze.vy, gaze.targetY, dt, 64, 17, 7);
    gaze.y = springNextValue; gaze.vy = springNextVelocity;
  }

  function setTargets(name) {
    const next = defs[name] || defs.idle;
    for (const key of numericFields) pose.target[key] = finite(next[key], pose.target[key]);
    pose.target.bodyTint = next.bodyTint || defs.idle.bodyTint;
    pose.target.accent = next.accent || defs.idle.accent;
    visualState = defs[name] ? name : 'idle';
    paintRequested = true;
  }

  function markInteraction(strength = 1) {
    if (strength > 0.15) lastStrongInteraction = performance.now();
    idleAction = null;
    paintRequested = true;
  }

  function scheduleNextIdle(now) {
    nextIdleAt = now + idleIntervals[idleIndex % idleIntervals.length] * 1000;
  }

  function scheduleNextBlink(now) {
    nextBlinkAt = now + blinkIntervals[(idleIndex + 1) % blinkIntervals.length] * 1000;
  }

  function updateIdle(now) {
    idleResult.lean = 0;
    idleResult.lift = 0;
    idleResult.glance = 0;
    idleResult.orbit = 0;
    const ambient = visualState === 'idle' || visualState === 'humming' || visualState === 'bored' || visualState === 'drowsy';
    if (!ambient || sequenceTimer || now - lastStrongInteraction < 30000) {
      idleAction = null;
      return idleResult;
    }
    if (!nextIdleAt) scheduleNextIdle(now);
    if (!idleAction && now >= nextIdleAt) {
      idleAction = { kind: idleActions[idleIndex % idleActions.length], started: now };
      idleIndex += 1;
      scheduleNextIdle(now);
    }
    if (!idleAction) return idleResult;
    const elapsed = now - idleAction.started;
    const duration = idleAction.kind === 'orbit-flash' ? 900 : idleAction.kind === 'double-glance' ? 1200 : 1050;
    if (elapsed >= duration) {
      idleAction = null;
      return idleResult;
    }
    const u = clamp(elapsed / duration, 0, 1);
    const wave = Math.sin(Math.PI * u) * motionScale;
    if (idleAction.kind === 'glance') {
      idleResult.lean = 2.2 * wave;
      idleResult.glance = 0.34 * wave;
    } else if (idleAction.kind === 'dip') {
      idleResult.lift = -2.7 * wave;
    } else if (idleAction.kind === 'tilt') {
      idleResult.lean = -2.7 * wave;
      idleResult.lift = 1.2 * wave;
      idleResult.glance = -0.2 * wave;
    } else if (idleAction.kind === 'double-glance') {
      const doubleWave = Math.sin(u * Math.PI * 4) * wave;
      idleResult.lean = 1.8 * doubleWave;
      idleResult.glance = 0.24 * doubleWave;
    } else {
      idleResult.orbit = wave;
    }
    return idleResult;
  }

  function updateBlink(now) {
    if (visualState === 'sleeping' || visualState === 'spawning' || visualState === 'powering-down') return 1;
    if (!nextBlinkAt) scheduleNextBlink(now);
    if (!blinkUntil && now >= nextBlinkAt) {
      blinkUntil = now + (reducedMotion ? 210 : 145);
      scheduleNextBlink(now);
    }
    if (!blinkUntil) return 1;
    const elapsed = now - (blinkUntil - (reducedMotion ? 210 : 145));
    const duration = reducedMotion ? 210 : 145;
    if (elapsed >= duration) {
      blinkUntil = 0;
      return 1;
    }
    const u = elapsed / duration;
    return clamp(Math.abs(u * 2 - 1) * 1.2, 0.06, 1);
  }

  function clearAmbientTimer() {
    if (!ambientTimer) return;
    clearTimeout(ambientTimer);
    ambientTimer = null;
  }

  function scheduleAmbientWake(now) {
    if (ambientTimer || document.hidden) return;
    let wakeAt = now + 60000;
    const ambient = visualState === 'idle' || visualState === 'humming'
      || visualState === 'bored' || visualState === 'drowsy';
    if (ambient && !sequenceTimer) {
      if (!nextIdleAt || nextIdleAt <= now) scheduleNextIdle(now);
      wakeAt = Math.min(wakeAt, nextIdleAt);
    }
    const blinkBlocked = visualState === 'sleeping' || visualState === 'spawning'
      || visualState === 'powering-down';
    if (!blinkBlocked) {
      if (!nextBlinkAt || nextBlinkAt <= now) scheduleNextBlink(now);
      wakeAt = Math.min(wakeAt, nextBlinkAt);
    }
    const delay = Math.max(80, Math.min(60000, wakeAt - now));
    ambientTimer = setTimeout(() => {
      ambientTimer = null;
      paintRequested = true;
      start();
    }, delay);
  }

  function pointsForMorph(morph) {
    const normalized = clamp(morph, -1, 1);
    return SHAPE_A.map((point, index) => {
      const other = SHAPE_B[index];
      const x = point[0] + (other[0] - point[0]) * normalized;
      const y = point[1] + (other[1] - point[1]) * normalized;
      return [x, y];
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
        result.lift += (8 + 12 * impulse.strength) * envelope;
        result.scaleY += 0.055 * envelope;
        result.scaleX -= 0.026 * envelope;
      } else if (impulse.kind === 'sway') {
        result.rotation += Math.sin(Math.PI * 2 * u) * (1.2 + 4.2 * impulse.strength) * (1 - 0.3 * u) * motionScale;
        result.scaleX += 0.022 * envelope;
      } else if (impulse.kind === 'spin') {
        result.rotation += Math.sin(Math.PI * u) * 11 * impulse.strength * motionScale;
      } else if (impulse.kind === 'burst') {
        result.lift += 5 * envelope;
        result.sparkle += envelope;
      }
    }
    return result;
  }

  function resizeCanvas() {
    if (!canvasContext) return null;
    const rect = canvas.getBoundingClientRect();
    // CSS breathing transforms the visible bounds, but must not resize the
    // backing bitmap on every frame. clientWidth/clientHeight are the layout
    // dimensions before that compositor-only transform.
    const width = canvas.clientWidth || 220;
    const height = canvas.clientHeight || 220;
    const dpr = clamp(finite(global.devicePixelRatio, 1), 1, 3);
    const pixelWidth = Math.max(1, Math.round(width * dpr));
    const pixelHeight = Math.max(1, Math.round(height * dpr));
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
      cachedCanvasGradients = null;
      sceneCache.clear();
      paintedCacheKey = '';
    }
    canvasScaleX = width / 220;
    canvasScaleY = height / 220;
    canvasContext.setTransform(canvasScaleX * dpr, 0, 0, canvasScaleY * dpr, 0, 0);
    return { x: rect.x, y: rect.y, width, height };
  }

  function getCanvasGradients(context) {
    if (cachedCanvasGradients) return cachedCanvasGradients;
    // Gradients are deliberately created once per canvas context. Recreating
    // several SVG-like gradients on every RAF tick grows QtWebEngine's
    // software raster cache even when the bitmap buffer itself is reused.
    cachedCanvasGradients = {
      shadow: context.createRadialGradient(110, 194, 0, 110, 194, 64),
      body: context.createLinearGradient(20, 20, 190, 205),
      sheen: context.createRadialGradient(60, 52, 0, 60, 52, 145),
      highlight: context.createLinearGradient(45, 40, 129, 127),
      environment: context.createLinearGradient(0, 145, 0, 198),
      lens: context.createRadialGradient(-10, -10, 1, 0, 0, 28),
    };
    cachedCanvasGradients.shadow.addColorStop(0, 'rgba(7,16,24,0.38)');
    cachedCanvasGradients.shadow.addColorStop(1, 'rgba(7,16,24,0)');
    cachedCanvasGradients.body.addColorStop(0, '#202633');
    cachedCanvasGradients.body.addColorStop(0.48, '#171c25');
    cachedCanvasGradients.body.addColorStop(1, '#111318');
    cachedCanvasGradients.sheen.addColorStop(0, 'rgba(255,255,255,0.68)');
    cachedCanvasGradients.sheen.addColorStop(0.32, 'rgba(143,199,255,0.22)');
    cachedCanvasGradients.sheen.addColorStop(1, 'rgba(143,199,255,0)');
    cachedCanvasGradients.highlight.addColorStop(0, 'rgba(214,236,255,0.38)');
    cachedCanvasGradients.highlight.addColorStop(0.24, 'rgba(133,189,255,0.08)');
    cachedCanvasGradients.highlight.addColorStop(0.58, 'rgba(133,189,255,0)');
    cachedCanvasGradients.environment.addColorStop(0, 'rgba(101,215,176,0)');
    cachedCanvasGradients.environment.addColorStop(0.72, 'rgba(101,215,176,0.04)');
    cachedCanvasGradients.environment.addColorStop(1, 'rgba(101,215,176,0.35)');
    cachedCanvasGradients.lens.addColorStop(0, '#e5f4ff');
    cachedCanvasGradients.lens.addColorStop(0.18, '#8cc8ff');
    cachedCanvasGradients.lens.addColorStop(0.68, '#3b79bc');
    cachedCanvasGradients.lens.addColorStop(1, '#1a355b');
    return cachedCanvasGradients;
  }

  function canvasBlob(context, points) {
    const tension = 0.92;
    context.beginPath();
    context.moveTo(points[0][0], points[0][1]);
    for (let index = 0; index < points.length; index += 1) {
      const p0 = points[(index - 1 + points.length) % points.length];
      const p1 = points[index];
      const p2 = points[(index + 1) % points.length];
      const p3 = points[(index + 2) % points.length];
      const c1x = p1[0] + (p2[0] - p0[0]) * tension / 6;
      const c1y = p1[1] + (p2[1] - p0[1]) * tension / 6;
      const c2x = p2[0] - (p3[0] - p1[0]) * tension / 6;
      const c2y = p2[1] - (p3[1] - p1[1]) * tension / 6;
      context.bezierCurveTo(c1x, c1y, c2x, c2y, p2[0], p2[1]);
    }
    context.closePath();
  }

  function canvasHighlight(context, current) {
    context.beginPath();
    context.moveTo(60 + current.highlightX * 0.08, 51 + current.highlightY * 0.08);
    context.bezierCurveTo(80, 38, 107, 33, 129, 39);
    context.bezierCurveTo(103, 55, 86, 76, 77, 106);
    context.bezierCurveTo(71, 125, 56, 127, 45, 113);
    context.bezierCurveTo(43, 91, 49, 67, 60 + current.highlightX * 0.08, 51 + current.highlightY * 0.08);
    context.closePath();
  }

  function canvasEnvironment(context) {
    context.beginPath();
    context.moveTo(42, 145);
    context.bezierCurveTo(67, 171, 104, 183, 142, 177);
    context.bezierCurveTo(156, 175, 169, 168, 180, 157);
    context.bezierCurveTo(174, 178, 159, 190, 141, 196);
    context.bezierCurveTo(114, 202, 80, 191, 61, 179);
    context.bezierCurveTo(50, 171, 43, 159, 42, 145);
    context.closePath();
  }

  function canvasOrbit(context, back, opacity, accent, tilt) {
    context.save();
    context.translate(110, 111);
    context.rotate((tilt + orbitAngle) * Math.PI / 180);
    context.translate(-110, -111);
    context.globalAlpha = opacity * (back ? 0.55 : 1);
    context.strokeStyle = accent;
    context.lineWidth = currentOrbitThickness + (back ? 0 : 0.35);
    context.setLineDash(back ? [3, 10] : [24, 92]);
    context.beginPath();
    context.ellipse(110, 111, 94, 43, 0, 0, Math.PI * 2);
    context.stroke();
    context.setLineDash([]);
    context.fillStyle = accent;
    const nodes = back ? [[29, 94, 1.8], [184, 132, 1.4]] : [[174, 84, 2.2], [78, 151, 1.2]];
    nodes.forEach(([x, y, radius]) => {
      context.beginPath();
      context.arc(x, y, radius, 0, Math.PI * 2);
      context.fill();
    });
    context.restore();
  }

  let currentOrbitThickness = 1.5;

  function syncSvgFace(current, gx, gy, blink) {
    // Keep the optical lens geometry in SVG for crisp edges and native event
    // compatibility. It is updated only during an event-driven paint window,
    // never by the ambient idle loop.
    if (bodyGroup.getAttribute('transform') !== lastGroupTransform) {
      bodyGroup.setAttribute('transform', lastGroupTransform);
    }
    if (lastSvgState !== visualState) {
      svg.dataset.state = visualState;
      lastSvgState = visualState;
    }
    const cssFaceTransform = `translate(${(gx * 9.5).toFixed(2)}px, ${(gy * 4.3).toFixed(2)}px) rotate(${(gx * 2.8 + gy * 1.2).toFixed(2)}deg)`;
    if (lastFaceTransform !== cssFaceTransform) {
      face.style.transform = cssFaceTransform;
      lastFaceTransform = cssFaceTransform;
    }

    // Expression geometry changes at state/blink cadence. Gaze itself is a
    // single group transform above; keeping the individual eye paths and
    // glints out of the high-frequency path avoids repeated SVG rasterization
    // in QtWebEngine's software compositor.
    const expressionKey = [
      current.eyeOpenL.toFixed(2), current.eyeOpenR.toFixed(2),
      current.eyeScaleX.toFixed(2), current.eyeScaleY.toFixed(2),
      current.eyeSpacing.toFixed(2), current.faceOffsetY.toFixed(2),
      current.focus.toFixed(2), current.pupilFocus.toFixed(2), blink.toFixed(2),
      gaze.targetX.toFixed(2), gaze.targetY.toFixed(2),
    ].join(':');
    if (expressionKey === lastFaceExpressionKey) return;
    lastFaceExpressionKey = expressionKey;
    const eyeSpacing = 26 + current.eyeSpacing;
    const faceY = 101 + current.faceOffsetY;
    const eyePositions = [-1, 1].map(side => ({
      x: 110 + side * eyeSpacing,
      y: faceY,
      angle: 0,
    }));
    eyePositions.forEach((position, index) => {
      const open = (index === 0 ? current.eyeOpenL : current.eyeOpenR) * blink;
      const eyeScaleX = current.eyeScaleX;
      const eyeScaleY = current.eyeScaleY * clamp(open, 0.05, 1.28);
      eyes[index].setAttribute('transform', `translate(${position.x.toFixed(2)} ${position.y.toFixed(2)}) scale(${eyeScaleX.toFixed(4)} ${eyeScaleY.toFixed(4)})`);
      const pupilX = clamp(gaze.targetX * 7.6 + (index === 0 ? -1 : 1) * gaze.targetX * 0.65, -8.2, 8.2);
      const pupilY = clamp(gaze.targetY * 5.8 - current.focus * 1.4, -6.8, 6.8);
      const pupilScale = clamp(0.82 + current.pupilFocus * 0.28, 0.76, 1.16);
      pupilEls[index].setAttribute('transform', `translate(${pupilX.toFixed(2)} ${pupilY.toFixed(2)}) scale(${pupilScale.toFixed(3)})`);
      glintEls[index][0].setAttribute('transform', `translate(${(pupilX - 2.2).toFixed(2)} ${(pupilY - 2.7).toFixed(2)})`);
      glintEls[index][1].setAttribute('transform', `translate(${(pupilX + 3.7).toFixed(2)} ${(pupilY + 3.4).toFixed(2)})`);
      lidEls[index].style.opacity = clamp(0.14 + (1 - open) * 0.36, 0.12, 0.62).toFixed(3);
    });
  }

  function render(now, dt) {
    const frame = resizeCanvas();
    if (!frame) return;
    const context = canvasContext;
    const idle = lastIdle;
    const impulse = impulseValues(now);
    const blink = lastBlink;
    const current = pose.current;
    const influence = clamp(current.gazeInfluence, 0, 1);
    const scan = (visualState === 'searching' || visualState === 'radar') ? Math.sin(now / 260) * 0.16 : 0;
    const gx = clamp((gaze.x + scan) * influence, -1, 1);
    const gy = clamp(gaze.y * influence, -1, 1);
    const rotation = current.bodyRotation + gx * 4.2 + idle.lean + impulse.rotation;
    const lift = current.bodyLift + idle.lift + impulse.lift;
    const breath = Math.sin(now / 1370) * 0.008 * motionScale;
    const scaleX = current.bodyScaleX * (1 + impulse.scaleX - breath * 0.32);
    const scaleY = current.bodyScaleY * (1 + impulse.scaleY + breath);
    lastSnapshotGroupTransform = `translate(110 110) rotate(${rotation.toFixed(2)}) skewX(${(current.bodySkew + gx * 1.7).toFixed(2)}) scale(${scaleX.toFixed(4)} ${scaleY.toFixed(4)}) translate(-110 ${(-110 - lift).toFixed(2)})`;
    const staticRotation = current.bodyRotation + idle.lean;
    const staticLift = current.bodyLift + idle.lift;
    // Breath is compositor-only on the Canvas layer; keep the SVG face's
    // parent transform stable between state changes and gaze updates.
    const staticScaleX = current.bodyScaleX;
    const staticScaleY = current.bodyScaleY;
    lastGroupTransform = `translate(110 110) rotate(${staticRotation.toFixed(2)}) skewX(${current.bodySkew.toFixed(2)}) scale(${staticScaleX.toFixed(4)} ${staticScaleY.toFixed(4)}) translate(-110 ${(-110 - staticLift).toFixed(2)})`;

    const accent = current.accent || '#59A8FF';
    const gradients = getCanvasGradients(context);
    const bodyPoints = pointsForMorph(current.morph + idle.lean * 0.012);
    const nextShapeKey = `${current.morph.toFixed(2)}:${idle.lean.toFixed(2)}`;
    if (nextShapeKey !== shapePathKey) {
      shapePath = blobPath(bodyPoints);
      shapePathKey = nextShapeKey;
    }
    const nextHighlightKey = `${current.highlightX.toFixed(3)}:${current.highlightY.toFixed(3)}`;
    if (nextHighlightKey !== highlightPathKey) {
      highlightPath = `M${(60 + current.highlightX * 0.08).toFixed(2)} ${(51 + current.highlightY * 0.08).toFixed(2)} C80 38 107 33 129 39 C103 55 86 76 77 106 C71 125 56 127 45 113 C43 91 49 67 60 51 Z`;
      highlightPathKey = nextHighlightKey;
    }

    syncSvgFace(current, gx, gy, blink);
    // The body/effects bitmap is state-scoped and deliberately independent of
    // gaze and short impulses. Those high-frequency changes are carried by
    // the crisp SVG face and compositor transforms, so interaction paints can
    // restore one cached bitmap instead of rerasterizing the full scene.
    const cacheKey = visualState;
    if (cacheKey && sceneCache.has(cacheKey)) {
      // A cached scene already occupies the canvas. Restoring it on every
      // gaze/impulse frame needlessly invalidates the software compositor;
      // restore only when the visual state actually changes.
      if (paintedCacheKey !== cacheKey) {
        context.clearRect(0, 0, 220, 220);
        context.putImageData(sceneCache.get(cacheKey), 0, 0);
        paintedCacheKey = cacheKey;
      }
      return;
    }
    context.clearRect(0, 0, 220, 220);
    context.lineJoin = 'round';
    context.lineCap = 'round';
    context.fillStyle = gradients.shadow;
    context.globalAlpha = clamp(current.shadowOpacity * 1.1, 0.04, 0.66);
    context.beginPath();
    context.ellipse(110, 194 - lift * 0.12, 61 * current.shadowScale * (1 - lift * 0.008), 7 * current.shadowScale, 0, 0, Math.PI * 2);
    context.fill();
    context.globalAlpha = 1;

    const orbitOpacity = clamp(current.orbitOpacity + idle.orbit * 0.35 + impulse.sparkle * 0.15, 0, 1);
    currentOrbitThickness = current.orbitThickness;
    orbitAngle += current.orbitSpeed * dt * 90 * motionScale;
    canvasOrbit(context, true, orbitOpacity, accent, current.orbitTilt);

    context.save();
    context.translate(110, 110);
    context.rotate(rotation * Math.PI / 180);
    context.transform(1, 0, Math.tan((current.bodySkew + gx * 1.7) * Math.PI / 180), 1, 0, 0);
    context.scale(scaleX, scaleY);
    context.translate(-110, -110 - lift);

    canvasBlob(context, bodyPoints);
    context.fillStyle = gradients.body;
    context.globalAlpha = 1;
    context.fill();
    context.strokeStyle = '#273346';
    context.lineWidth = 1.2;
    context.stroke();

    canvasBlob(context, bodyPoints);
    // The alpha-tuned layers retain the glow without asking the software
    // compositor to allocate a new screen-blend surface every frame.
    context.globalCompositeOperation = 'source-over';
    context.globalAlpha = clamp(0.18 + current.glow * 0.34 + current.pulse * 0.08, 0, 0.86);
    context.fillStyle = gradients.sheen;
    context.fill();

    canvasHighlight(context, current);
    context.globalAlpha = clamp(0.18 + current.glow * 0.58, 0, 0.88);
    context.fillStyle = gradients.highlight;
    context.fill();

    canvasEnvironment(context);
    context.globalAlpha = clamp(0.18 + current.glow * 0.4, 0, 0.74);
    context.fillStyle = gradients.environment;
    context.fill();

    canvasBlob(context, bodyPoints);
    context.globalAlpha = clamp(current.rimIntensity + current.glow * 0.08 + impulse.sparkle * 0.12, 0, 1);
    context.strokeStyle = accent;
    context.lineWidth = 1.4;
    context.stroke();

    context.restore();

    canvasOrbit(context, false, orbitOpacity, accent, current.orbitTilt);
    const pulseWave = current.pulse > 0.01 ? (0.5 + 0.5 * Math.sin(now / (reducedMotion ? 660 : 420))) * current.pulse : 0;
    const particlePower = clamp(current.sparkle + impulse.sparkle + current.particleRate * 0.28 + pulseWave * 0.18, 0, 1);
    context.fillStyle = accent;
    particles.forEach((particle, index) => {
      const phase = now / (720 + index * 87) + index * 1.7;
      const opacity = particlePower * (0.28 + 0.72 * (0.5 + 0.5 * Math.sin(phase)));
      const x = finite(particle.getAttribute('cx'), 110);
      const y = finite(particle.getAttribute('cy'), 110);
      context.globalAlpha = opacity;
      context.beginPath();
      context.arc(x, y, 0.65 + opacity * 1.2, 0, Math.PI * 2);
      context.fill();
    });
    if (current.warning > 0.05) {
      context.globalAlpha = clamp(current.warning * (0.45 + pulseWave * 0.65), 0, 1);
      context.strokeStyle = accent;
      context.lineWidth = 2.2;
      context.beginPath();
      context.moveTo(110, 143);
      context.lineTo(110, 153);
      context.moveTo(110, 159);
      context.lineTo(110, 159.5);
      context.stroke();
    }
    context.globalAlpha = 1;
    if (cacheKey) {
      if (sceneCache.has(cacheKey)) sceneCache.delete(cacheKey);
      sceneCache.set(cacheKey, context.getImageData(0, 0, canvas.width, canvas.height));
      while (sceneCache.size > SCENE_CACHE_LIMIT) {
        sceneCache.delete(sceneCache.keys().next().value);
      }
      paintedCacheKey = cacheKey;
    }
  }

  function frame(now) {
    if (!raf) return;
    if (!lastFrame || now - lastFrame > 500) lastFrame = now;
    const dt = clamp((now - lastFrame) / 1000, 0, 0.05);
    lastFrame = now;
    interpolatePose(dt);
    lastIdle = updateIdle(now);
    lastBlink = updateBlink(now);
    const impulseActive = (trickImpulse && now - trickImpulse.started < trickImpulse.duration)
      || (releaseImpulse && now - releaseImpulse.started < releaseImpulse.duration);
    const ambientActive = Boolean(idleAction || blinkUntil);
    // Ambient breathing is compositor-only CSS. Avoid keeping a JavaScript
    // RAF alive once the pose is settled; event methods restart it for the
    // short gaze/release windows that need real-time sampling.
    const needsFrame = paintRequested || impulseActive || ambientActive;
    const paintInterval = ambientActive ? 80 : 32;
    if (needsFrame
        && now - lastPaint >= paintInterval) {
      render(now, dt);
      lastPaint = now;
      paintRequested = false;
    }
    if (needsFrame) {
      raf = requestAnimationFrame(frame);
    } else {
      raf = null;
      lastFrame = 0;
      scheduleAmbientWake(now);
    }
  }

  function start() {
    clearAmbientTimer();
    if (raf) return;
    lastFrame = performance.now();
    raf = requestAnimationFrame(frame);
  }

  function stop() {
    clearAmbientTimer();
    if (!raf) return;
    cancelAnimationFrame(raf);
    raf = null;
    lastFrame = 0;
  }

  function runTrick(kind, strength = 1) {
    const safeKind = ['bounce', 'sway', 'spin', 'burst'].includes(kind) ? kind : '';
    if (!safeKind) return;
    const safeStrength = clamp(finite(strength, 1), 0, 1);
    trickImpulse = { kind: safeKind, strength: safeStrength, started: performance.now(), duration: safeKind === 'burst' ? 720 : 900 };
    markInteraction(safeStrength);
  }

  function setState(name) {
    const safeName = defs[name] ? name : 'idle';
    persistentState = safeName;
    const locked = ['listening', 'dictating', 'loading', 'thinking', 'working', 'writing', 'sending', 'dragging', 'powering-down'];
    if (sequenceTimer && (locked.includes(safeName) || locked.includes(visualState))) {
      clearTimeout(sequenceTimer);
      sequenceTimer = null;
      sequenceToken += 1;
    }
    setTargets(safeName);
    if (safeName !== 'idle') markInteraction(0.2);
    start();
  }

  function sequence(steps) {
    const list = Array.isArray(steps) ? steps.filter(step => step && defs[step.state]) : [];
    clearTimeout(sequenceTimer);
    const token = ++sequenceToken;
    let index = 0;
    function next() {
      if (token !== sequenceToken) return;
      if (index >= list.length) {
        sequenceTimer = null;
        setTargets(persistentState);
        return;
      }
      const step = list[index++];
      setTargets(step.state);
      runTrick(step.trick || '', step.strength == null ? 1 : step.strength);
      const duration = clamp(finite(step.ms, 900), 1, 30000);
      sequenceTimer = setTimeout(next, duration);
      start();
    }
    next();
  }

  function enter() {
    sequence([{ state: 'spawning', ms: 520, trick: 'burst', strength: 0.76 },
      { state: 'waking', ms: 880, trick: '' },
      { state: 'idle', ms: 460, trick: '' }]);
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
    gaze.x = tx;
    gaze.y = ty;
    gaze.vx = 0;
    gaze.vy = 0;
    gazeReturnToken += 1;
    if (gazeReturnTimer) {
      clearTimeout(gazeReturnTimer);
      gazeReturnTimer = null;
    }
    face.classList.remove('gaze-return');
    gaze.active = true;
    gaze.input = { x: finite(x), y: finite(y), width: viewWidth, height: viewHeight, nx, ny, active: true };
    paintRequested = true;
    start();
  }

  function clearGaze() {
    gaze.targetX = 0;
    gaze.targetY = 0;
    gaze.x = 0;
    gaze.y = 0;
    gaze.vx = 0;
    gaze.vy = 0;
    const token = ++gazeReturnToken;
    face.classList.add('gaze-return');
    if (gazeReturnTimer) clearTimeout(gazeReturnTimer);
    gazeReturnTimer = setTimeout(() => {
      if (token === gazeReturnToken) {
        face.classList.remove('gaze-return');
        gazeReturnTimer = null;
      }
    }, 420);
    gaze.active = false;
    gaze.input = { x: gaze.input.width / 2, y: gaze.input.height / 2, width: gaze.input.width, height: gaze.input.height, nx: 0.5, ny: 0.5, active: false };
    paintRequested = true;
    start();
  }

  function dragRelease(kind, strength) {
    if (kind !== 'bounce' && kind !== 'sway') return;
    releaseImpulse = { kind, strength: clamp(finite(strength), 0, 1), started: performance.now(), duration: kind === 'bounce' ? 820 : 900 };
    markInteraction(releaseImpulse.strength);
    paintRequested = true;
    start();
  }

  function snapshot() {
    return {
      state: visualState,
      mode: 'hold',
      persistentState,
      sequenceActive: Boolean(sequenceTimer),
      reducedMotion,
      diagnostics: {
        rafActive: Boolean(raf),
        ambientTimerActive: Boolean(ambientTimer),
        sequenceTimerActive: Boolean(sequenceTimer),
        gazeReturnTimerActive: Boolean(gazeReturnTimer),
        sceneCacheEntries: sceneCache.size,
      },
    };
  }

  function gazeSnapshot() {
    return {
      target: { x: gaze.targetX, y: gaze.targetY },
      pointer: { x: gaze.x, y: gaze.y },
      input: Object.assign({}, gaze.input),
      pose: { turn: pose.current.bodyRotation + gaze.x * 4.2, tilt: gaze.y * 4.3, roll: pose.current.bodySkew },
    };
  }

  function renderSnapshot() {
    const svgRect = (canvas || svg).getBoundingClientRect();
    const width = svgRect.width || 220;
    const height = svgRect.height || 220;
    const scaleX = width / 220;
    const scaleY = height / 220;
    const current = pose.current;
    const influence = clamp(current.gazeInfluence, 0, 1);
    const scan = (visualState === 'searching' || visualState === 'radar') ? Math.sin(performance.now() / 260) * 0.16 : 0;
    const gx = clamp((gaze.x + scan) * influence, -1, 1);
    const gy = clamp(gaze.y * influence, -1, 1);
    const bodyWidth = 160 * Math.abs(current.bodyScaleX) * scaleX;
    const bodyHeight = 172 * Math.abs(current.bodyScaleY) * scaleY;
    const bodyRect = {
      x: svgRect.x + (110 * scaleX - bodyWidth / 2),
      y: svgRect.y + (110 * scaleY - bodyHeight / 2),
      width: bodyWidth,
      height: bodyHeight,
    };
    const eyeSpacing = 26 + current.eyeSpacing;
    const faceY = 101 + current.faceOffsetY + gy * 4.3;
    const blink = visualState === 'sleeping' ? 0.2 : 1;
    const eyePositions = [-1, 1].map(side => ({
      x: 110 + side * eyeSpacing + gx * 9.5,
      y: faceY + Math.abs(gx) * 0.7,
      angle: side * gx * 2.8 + gy * 1.2,
    }));
    const eyeSnapshots = eyePositions.map((position, index) => {
      const open = (index === 0 ? current.eyeOpenL : current.eyeOpenR) * blink;
      const eyeScaleX = current.eyeScaleX * (1 + Math.abs(gx) * 0.025);
      const eyeScaleY = current.eyeScaleY * clamp(open, 0.05, 1.28);
      const eyeWidth = 40 * eyeScaleX * scaleX;
      const eyeHeight = 30 * eyeScaleY * scaleY;
      const pupilX = clamp(gx * 7.6 + (index === 0 ? -1 : 1) * gx * 0.65, -8.2, 8.2);
      const pupilY = clamp(gy * 5.8 - current.focus * 1.4, -6.8, 6.8);
      const pupilScale = clamp(0.82 + current.pupilFocus * 0.28, 0.76, 1.16);
      return {
        x: svgRect.x + position.x * scaleX - eyeWidth / 2,
        y: svgRect.y + position.y * scaleY - eyeHeight / 2,
        width: eyeWidth,
        height: eyeHeight,
        transform: `translate(${position.x.toFixed(2)} ${position.y.toFixed(2)}) rotate(${position.angle.toFixed(2)}) scale(${eyeScaleX.toFixed(4)} ${eyeScaleY.toFixed(4)})`,
        dLength: 150,
        pupil: `translate(${pupilX.toFixed(2)} ${pupilY.toFixed(2)}) scale(${pupilScale.toFixed(3)})`,
      };
    });
    if (!shapePath) shapePath = blobPath(pointsForMorph(current.morph));
    return {
      target: { x: gaze.targetX, y: gaze.targetY },
      pointer: { x: gaze.x, y: gaze.y },
      input: Object.assign({}, gaze.input),
      pose: { turn: pose.current.bodyRotation + gaze.x * 4.2, tilt: gaze.y * 4.3, roll: pose.current.bodySkew },
      svg: { x: svgRect.x, y: svgRect.y, width, height },
      groupTransform: lastSnapshotGroupTransform || lastGroupTransform,
      bodyPath: shapePath,
      body: { x: bodyRect.x, y: bodyRect.y, width: bodyRect.width, height: bodyRect.height },
      eyes: eyeSnapshots,
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
