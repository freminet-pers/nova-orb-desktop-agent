/* Nova Orb state targets. The renderer is the only writer of SVG transforms. */
(function (global) {
  'use strict';

  const BASE = {
    bodyScaleX: 1,
    bodyScaleY: 1,
    bodyRotation: 0,
    bodyLift: 0,
    bodySkew: 0,
    morph: 0,
    eyeOpenL: 1,
    eyeOpenR: 1,
    eyeScaleX: 1,
    eyeScaleY: 1,
    eyeSpacing: 0,
    pupilFocus: 0.4,
    focus: 0.4,
    faceOffsetY: 0,
    gazeInfluence: 1,
    bodyTint: '#111318',
    accent: '#59A8FF',
    rimIntensity: 0.28,
    glow: 0.28,
    highlightX: -30,
    highlightY: -36,
    shadowScale: 1,
    shadowOpacity: 0.42,
    orbitOpacity: 0,
    orbitSpeed: 0,
    orbitTilt: -18,
    orbitThickness: 1.5,
    particleRate: 0,
    particleLife: 0.6,
    sparkle: 0,
    pulse: 0,
    warning: 0,
  };

  const state = (overrides) => Object.freeze(Object.assign({}, BASE, overrides));

  const STATES = {
    idle: state({ glow: 0.24, rimIntensity: 0.24, idleMode: 'alive' }),
    sleeping: state({
      eyeOpenL: 0.14, eyeOpenR: 0.14, eyeScaleY: 0.92, faceOffsetY: 5,
      bodyScaleY: 0.97, bodyLift: -2, gazeInfluence: 0.14, glow: 0.12,
      accent: '#8B7CFF', shadowOpacity: 0.48,
    }),
    waking: state({
      bodyScaleX: 0.88, bodyScaleY: 0.76, bodyLift: 1, morph: -0.08,
      eyeOpenL: 0.46, eyeOpenR: 0.46, eyeScaleY: 0.7, gazeInfluence: 0.4,
      orbitOpacity: 0.42, orbitSpeed: 0.35, pulse: 0.52, glow: 0.58,
    }),
    listening: state({
      eyeScaleX: 1.04, eyeScaleY: 1.05, pupilFocus: 0.72, gazeInfluence: 0.6,
      rimIntensity: 0.8, glow: 0.48, pulse: 0.72, orbitOpacity: 0.18,
    }),
    thinking: state({
      eyeScaleX: 1.02, eyeScaleY: 1.04, pupilFocus: 0.84, faceOffsetY: -2,
      gazeInfluence: 0.4, accent: '#8B7CFF', rimIntensity: 0.68, glow: 0.55,
      orbitOpacity: 0.86, orbitSpeed: 0.62, orbitTilt: -24, orbitThickness: 1.8,
      particleRate: 0.24,
    }),
    searching: state({
      eyeScaleX: 1.06, pupilFocus: 0.9, gazeInfluence: 0.52,
      rimIntensity: 0.84, glow: 0.58, orbitOpacity: 0.94, orbitSpeed: 1.2,
      orbitTilt: -28, orbitThickness: 1.55, particleRate: 0.3,
    }),
    working: state({
      eyeScaleX: 1.03, pupilFocus: 0.78, gazeInfluence: 0.44,
      rimIntensity: 0.72, glow: 0.5, orbitOpacity: 0.82, orbitSpeed: 0.82,
      orbitTilt: -20, orbitThickness: 1.7, particleRate: 0.38,
    }),
    excited: state({
      bodyScaleX: 1.02, bodyScaleY: 1.05, bodyLift: 7, morph: 0.16,
      eyeScaleX: 1.04, eyeScaleY: 0.86, pupilFocus: 0.58, gazeInfluence: 0.8,
      accent: '#65D7B0', glow: 0.58, rimIntensity: 0.64, pulse: 0.5, sparkle: 0.42,
    }),
    surprised: state({
      bodyScaleX: 0.96, bodyScaleY: 1.07, bodyLift: 3, morph: -0.12,
      eyeScaleX: 1.14, eyeScaleY: 1.18, pupilFocus: 0.9, gazeInfluence: 0.82,
      rimIntensity: 0.66, glow: 0.56, pulse: 0.44,
    }),
    suspicious: state({
      bodyRotation: -4.2, bodySkew: -1.4, morph: -0.16, eyeOpenL: 0.72,
      eyeOpenR: 0.88, eyeScaleY: 0.78, eyeSpacing: -1.5, pupilFocus: 0.62,
      gazeInfluence: 0.78, accent: '#F1B45B', glow: 0.36, rimIntensity: 0.54,
    }),
    angry: state({
      bodyRotation: -3.6, bodySkew: -1.8, morph: 0.12, eyeOpenL: 0.5,
      eyeOpenR: 0.58, eyeScaleY: 0.66, eyeSpacing: -2, pupilFocus: 0.76,
      gazeInfluence: 0.54, accent: '#E98B86', glow: 0.35, rimIntensity: 0.5,
    }),
    drowsy: state({
      bodyScaleY: 0.98, bodyLift: -1, morph: -0.12, eyeOpenL: 0.32,
      eyeOpenR: 0.28, eyeScaleY: 0.66, faceOffsetY: 3, gazeInfluence: 0.28,
      accent: '#8B7CFF', glow: 0.18, rimIntensity: 0.2,
    }),
    happy: state({
      bodyScaleX: 1.01, bodyScaleY: 1.02, bodyLift: 4, morph: 0.12,
      eyeScaleX: 1.02, eyeScaleY: 0.7, pupilFocus: 0.48, gazeInfluence: 0.86,
      accent: '#65D7B0', glow: 0.46, rimIntensity: 0.56, pulse: 0.28,
    }),
    curious: state({
      bodyRotation: 2.8, bodySkew: 0.8, morph: -0.08, eyeScaleX: 1.04,
      eyeScaleY: 0.96, pupilFocus: 0.68, gazeInfluence: 0.92,
      accent: '#59A8FF', glow: 0.38, rimIntensity: 0.42,
    }),
    confused: state({
      bodyRotation: 5.2, bodySkew: 1.8, morph: 0.2, eyeOpenL: 0.74,
      eyeOpenR: 0.92, eyeScaleY: 0.78, eyeSpacing: 1.5, pupilFocus: 0.55,
      gazeInfluence: 0.7, accent: '#F1B45B', glow: 0.32, rimIntensity: 0.45,
    }),
    bored: state({
      bodyScaleY: 0.98, bodyLift: -1, morph: 0.05, eyeOpenL: 0.54,
      eyeOpenR: 0.54, eyeScaleY: 0.72, pupilFocus: 0.28, gazeInfluence: 0.35,
      accent: '#8B7CFF', glow: 0.2, rimIntensity: 0.24,
    }),
    proud: state({
      bodyScaleX: 1.02, bodyScaleY: 1.03, bodyLift: 5, morph: -0.04,
      eyeScaleY: 0.78, faceOffsetY: -3, pupilFocus: 0.68, gazeInfluence: 0.7,
      accent: '#65D7B0', glow: 0.46, rimIntensity: 0.58, pulse: 0.32,
    }),
    shy: state({
      bodyScaleX: 0.98, bodyScaleY: 0.98, bodyLift: -1, morph: 0.18,
      eyeOpenL: 0.64, eyeOpenR: 0.64, eyeScaleY: 0.7, eyeSpacing: 1,
      pupilFocus: 0.36, gazeInfluence: 0.45, accent: '#8B7CFF', glow: 0.3,
    }),
    sad: state({
      bodyScaleY: 0.97, bodyLift: -3, morph: -0.22, eyeOpenL: 0.65,
      eyeOpenR: 0.65, eyeScaleY: 0.82, faceOffsetY: 3, pupilFocus: 0.3,
      gazeInfluence: 0.4, accent: '#8B7CFF', glow: 0.18, rimIntensity: 0.2,
    }),
    laughing: state({
      bodyScaleX: 1.03, bodyScaleY: 1.04, bodyLift: 6, morph: 0.18,
      eyeOpenL: 0.4, eyeOpenR: 0.4, eyeScaleY: 0.48, pupilFocus: 0.42,
      gazeInfluence: 0.7, accent: '#65D7B0', glow: 0.5, rimIntensity: 0.6, sparkle: 0.22,
    }),
    scared: state({
      bodyScaleX: 0.96, bodyScaleY: 1.04, morph: -0.25, eyeOpenL: 0.88,
      eyeOpenR: 0.92, eyeScaleX: 0.9, eyeScaleY: 1.08, pupilFocus: 0.94,
      gazeInfluence: 0.86, accent: '#F1B45B', glow: 0.42, rimIntensity: 0.55,
    }),
    playful: state({
      bodyScaleX: 1.04, bodyScaleY: 0.96, bodyLift: 5, morph: 0.24,
      bodyRotation: -2.4, eyeScaleX: 1.04, eyeScaleY: 0.86, pupilFocus: 0.54,
      gazeInfluence: 0.9, accent: '#65D7B0', glow: 0.48, rimIntensity: 0.6, sparkle: 0.18,
    }),
    celebrate: state({
      bodyScaleX: 1.06, bodyScaleY: 1.08, bodyLift: 9, morph: 0.24,
      eyeScaleX: 1.06, eyeScaleY: 0.68, pupilFocus: 0.55, gazeInfluence: 0.82,
      accent: '#65D7B0', glow: 0.72, rimIntensity: 0.88, pulse: 0.9, sparkle: 1,
      particleRate: 0.8,
    }),
    orbit: state({
      accent: '#8B7CFF', rimIntensity: 0.7, glow: 0.52, orbitOpacity: 0.82,
      orbitSpeed: 0.48, orbitTilt: -23, orbitThickness: 1.8, particleRate: 0.28,
    }),
    radar: state({
      eyeScaleX: 1.04, pupilFocus: 0.88, gazeInfluence: 0.5,
      accent: '#59A8FF', rimIntensity: 0.78, glow: 0.55, orbitOpacity: 0.95,
      orbitSpeed: 1.36, orbitTilt: -32, orbitThickness: 1.4, pulse: 0.24,
    }),
    progress: state({
      accent: '#59A8FF', rimIntensity: 0.7, glow: 0.5, orbitOpacity: 0.86,
      orbitSpeed: 0.7, orbitTilt: -16, orbitThickness: 2.1, particleRate: 0.5,
    }),
    spawning: state({
      bodyScaleX: 0.14, bodyScaleY: 0.14, bodyLift: 0, morph: -0.18,
      eyeOpenL: 0.04, eyeOpenR: 0.04, eyeScaleX: 0.2, eyeScaleY: 0.2,
      gazeInfluence: 0.2, accent: '#59A8FF', rimIntensity: 1, glow: 1,
      orbitOpacity: 1, orbitSpeed: 0.85, orbitTilt: -26, orbitThickness: 2.2,
      particleRate: 1, particleLife: 1, sparkle: 0.8, pulse: 1,
    }),
    humming: state({
      eyeScaleY: 0.9, pupilFocus: 0.5, gazeInfluence: 0.74,
      accent: '#59A8FF', rimIntensity: 0.44, glow: 0.36, orbitOpacity: 0.2,
      orbitSpeed: 0.2, pulse: 0.26,
    }),
    loading: state({
      eyeScaleX: 1.02, pupilFocus: 0.74, gazeInfluence: 0.52,
      accent: '#59A8FF', rimIntensity: 0.76, glow: 0.48, orbitOpacity: 0.38,
      orbitSpeed: 0.72, orbitTilt: -10, pulse: 0.32,
    }),
    dictating: state({
      eyeScaleX: 1.04, pupilFocus: 0.76, gazeInfluence: 0.62,
      accent: '#59A8FF', rimIntensity: 0.82, glow: 0.52, orbitOpacity: 0.28,
      orbitSpeed: 0.42, pulse: 0.65,
    }),
    writing: state({
      eyeScaleX: 1.03, pupilFocus: 0.72, gazeInfluence: 0.48,
      accent: '#8B7CFF', rimIntensity: 0.72, glow: 0.46, orbitOpacity: 0.54,
      orbitSpeed: 0.55, orbitTilt: -15, particleRate: 0.2,
    }),
    sending: state({
      bodyScaleX: 0.96, bodyScaleY: 0.96, bodyLift: 4, morph: -0.08,
      eyeScaleX: 1.02, pupilFocus: 0.82, gazeInfluence: 0.58,
      accent: '#59A8FF', rimIntensity: 0.82, glow: 0.6, orbitOpacity: 0.64,
      orbitSpeed: 0.86, pulse: 0.84,
    }),
    receiving: state({
      bodyScaleX: 1.02, bodyScaleY: 1.01, bodyLift: 2, morph: 0.08,
      eyeScaleY: 0.88, pupilFocus: 0.58, gazeInfluence: 0.74,
      accent: '#65D7B0', rimIntensity: 0.76, glow: 0.72, orbitOpacity: 0.34,
      pulse: 0.82, sparkle: 0.18,
    }),
    uploading: state({
      accent: '#59A8FF', rimIntensity: 0.7, glow: 0.48, orbitOpacity: 0.74,
      orbitSpeed: 0.74, orbitTilt: -34, pulse: 0.4, particleRate: 0.42,
    }),
    notifying: state({
      accent: '#65D7B0', rimIntensity: 0.82, glow: 0.62, orbitOpacity: 0.22,
      pulse: 0.8, sparkle: 0.68,
    }),
    alerting: state({
      bodyScaleX: 0.98, bodyScaleY: 1.02, morph: -0.1, eyeOpenL: 0.58,
      eyeOpenR: 0.62, eyeScaleY: 0.7, gazeInfluence: 0.55,
      accent: '#F1B45B', rimIntensity: 0.9, glow: 0.5, pulse: 0.96, warning: 0.72,
    }),
    dragging: state({
      bodyScaleX: 1.02, bodyScaleY: 0.98, bodyLift: 1, morph: 0.06,
      eyeScaleX: 1.02, pupilFocus: 0.84, gazeInfluence: 0.66,
      accent: '#59A8FF', rimIntensity: 0.68, glow: 0.46, orbitOpacity: 0.22,
      orbitSpeed: 0.22,
    }),
    bouncing: state({
      bodyScaleX: 1.04, bodyScaleY: 0.9, bodyLift: 7, morph: 0.18,
      eyeScaleY: 0.78, pupilFocus: 0.56, gazeInfluence: 0.82,
      accent: '#65D7B0', rimIntensity: 0.64, glow: 0.52, pulse: 0.5,
    }),
    'powering-down': state({
      bodyScaleX: 0.2, bodyScaleY: 0.2, bodyLift: -1, morph: -0.2,
      eyeOpenL: 0.08, eyeOpenR: 0.08, eyeScaleX: 0.2, eyeScaleY: 0.2,
      gazeInfluence: 0.1, accent: '#59A8FF', rimIntensity: 0.96, glow: 0.9,
      orbitOpacity: 0.76, orbitSpeed: 0.95, orbitTilt: -26, pulse: 0.78, sparkle: 0.55,
    }),
    // Product-result states are intentionally outside the legacy 39-state
    // groups. They give model/tool completion a direct visual target while
    // the historical behavior table remains unchanged.
    saved: state({
      accent: '#65D7B0', rimIntensity: 0.86, glow: 0.68, orbitOpacity: 0.24,
      pulse: 0.86, sparkle: 0.82,
    }),
    launched: state({
      bodyScaleX: 1.02, bodyScaleY: 1.03, bodyLift: 5, morph: -0.04,
      eyeScaleY: 0.78, pupilFocus: 0.7, gazeInfluence: 0.7,
      accent: '#65D7B0', rimIntensity: 0.68, glow: 0.54, pulse: 0.5, sparkle: 0.46,
    }),
    reply: state({
      bodyScaleX: 1.01, bodyScaleY: 1.01, bodyLift: 2, morph: 0.06,
      eyeScaleY: 0.86, pupilFocus: 0.56, gazeInfluence: 0.76,
      accent: '#65D7B0', rimIntensity: 0.74, glow: 0.64, pulse: 0.7, sparkle: 0.18,
    }),
    error: state({
      bodyScaleX: 0.98, bodyScaleY: 1.02, morph: -0.12, eyeOpenL: 0.56,
      eyeOpenR: 0.62, eyeScaleY: 0.7, gazeInfluence: 0.56,
      accent: '#F1B45B', rimIntensity: 0.86, glow: 0.46, pulse: 0.9, warning: 0.68,
    }),
  };

  const GROUPS = {
    Lifecycle: ['sleeping', 'waking', 'idle', 'listening', 'thinking', 'searching', 'working'],
    Reactions: ['excited', 'surprised', 'suspicious', 'angry', 'drowsy', 'happy', 'curious',
      'confused', 'bored', 'proud', 'shy', 'sad', 'laughing', 'scared', 'playful', 'celebrate'],
    'Agent morphs': ['orbit', 'radar', 'progress'],
    'Product lifecycle': ['spawning', 'humming', 'loading', 'dictating', 'writing', 'sending',
      'receiving', 'uploading', 'notifying', 'alerting', 'dragging', 'bouncing', 'powering-down'],
  };

  global.NOVA_STATE_DEFS = Object.freeze(STATES);
  global.NOVA_STATE_GROUPS = Object.freeze(GROUPS);
  global.NOVA_VISUAL_STATES = Object.freeze(Object.keys(STATES));
})(window);
