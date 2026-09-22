/* Nova v0.2.0 visual targets. Business names remain compatible; the renderer
 * composes them from a small set of warm, restrained pose primitives. */
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
    pupilFocus: 0.42,
    focus: 0.36,
    faceOffsetY: 0,
    gazeInfluence: 1,
    bodyTint: '#f7f0e5',
    accent: '#9a886f',
    rimIntensity: 0.25,
    glow: 0.12,
    highlightX: -28,
    highlightY: -34,
    shadowScale: 1,
    shadowOpacity: 0.22,
    subsurface: 0.72,
    orbitOpacity: 0,
    orbitSpeed: 0,
    orbitTilt: -14,
    orbitThickness: 1.25,
    particleRate: 0,
    particleLife: 0.6,
    sparkle: 0,
    pulse: 0,
    warning: 0,
    mouth: 0,
  };

  const state = overrides => Object.freeze(Object.assign({}, BASE, overrides));

  const STATES = {
    idle: state({ glow: 0.12, rimIntensity: 0.22, idleMode: 'alive' }),
    sleeping: state({
      eyeOpenL: 0.15, eyeOpenR: 0.14, eyeScaleY: 0.88, faceOffsetY: 5,
      bodyScaleY: 0.975, bodyLift: -2, gazeInfluence: 0.12, glow: 0.05,
      accent: '#9b907f', shadowOpacity: 0.25,
    }),
    waking: state({
      bodyScaleX: 0.82, bodyScaleY: 0.72, bodyLift: -1, morph: -0.08,
      eyeOpenL: 0.32, eyeOpenR: 0.3, eyeScaleY: 0.72, gazeInfluence: 0.35,
      orbitOpacity: 0.24, orbitSpeed: 0.32, pulse: 0.34, glow: 0.3,
      accent: '#a18b71',
    }),
    listening: state({
      eyeScaleX: 1.04, eyeScaleY: 1.05, pupilFocus: 0.68, gazeInfluence: 0.62,
      rimIntensity: 0.62, glow: 0.2, pulse: 0.56, orbitOpacity: 0.08,
      accent: '#a18b71',
    }),
    thinking: state({
      eyeScaleX: 1.015, eyeScaleY: 1.04, pupilFocus: 0.78, faceOffsetY: -2,
      gazeInfluence: 0.44, accent: '#7f9080', rimIntensity: 0.58, glow: 0.2,
      orbitOpacity: 0.58, orbitSpeed: 0.48, orbitTilt: -22, orbitThickness: 1.35,
      particleRate: 0.1,
    }),
    searching: state({
      eyeScaleX: 1.04, pupilFocus: 0.82, gazeInfluence: 0.56,
      rimIntensity: 0.72, glow: 0.25, orbitOpacity: 0.68, orbitSpeed: 0.8,
      orbitTilt: -27, orbitThickness: 1.3, particleRate: 0.14,
      accent: '#8d947d',
    }),
    working: state({
      eyeScaleX: 1.025, pupilFocus: 0.72, gazeInfluence: 0.48,
      rimIntensity: 0.62, glow: 0.18, orbitOpacity: 0.48, orbitSpeed: 0.58,
      orbitTilt: -18, orbitThickness: 1.35, particleRate: 0.16,
      accent: '#88917f',
    }),
    excited: state({
      bodyScaleX: 1.02, bodyScaleY: 1.05, bodyLift: 6, morph: 0.14,
      eyeScaleX: 1.04, eyeScaleY: 0.82, pupilFocus: 0.5, gazeInfluence: 0.8,
      accent: '#8c997c', glow: 0.25, rimIntensity: 0.52, pulse: 0.4, sparkle: 0.26,
    }),
    surprised: state({
      bodyScaleX: 0.97, bodyScaleY: 1.06, bodyLift: 2, morph: -0.1,
      eyeScaleX: 1.12, eyeScaleY: 1.16, pupilFocus: 0.84, gazeInfluence: 0.84,
      rimIntensity: 0.5, glow: 0.22, pulse: 0.34,
    }),
    suspicious: state({
      bodyRotation: -4, bodySkew: -1.1, morph: -0.14, eyeOpenL: 0.7,
      eyeOpenR: 0.88, eyeScaleY: 0.8, eyeSpacing: -1.2, pupilFocus: 0.56,
      gazeInfluence: 0.76, accent: '#a48b67', glow: 0.13, rimIntensity: 0.4,
    }),
    angry: state({
      bodyRotation: -3.3, bodySkew: -1.4, morph: 0.1, eyeOpenL: 0.48,
      eyeOpenR: 0.56, eyeScaleY: 0.62, eyeSpacing: -1.7, pupilFocus: 0.7,
      gazeInfluence: 0.52, accent: '#b87865', glow: 0.12, rimIntensity: 0.38,
    }),
    drowsy: state({
      bodyScaleY: 0.98, bodyLift: -1, morph: -0.1, eyeOpenL: 0.3,
      eyeOpenR: 0.27, eyeScaleY: 0.64, faceOffsetY: 3, gazeInfluence: 0.26,
      accent: '#9b907f', glow: 0.06, rimIntensity: 0.18,
    }),
    happy: state({
      bodyScaleX: 1.01, bodyScaleY: 1.02, bodyLift: 3, morph: 0.1,
      eyeScaleX: 1.02, eyeScaleY: 0.7, pupilFocus: 0.42, gazeInfluence: 0.86,
      accent: '#879a7e', glow: 0.18, rimIntensity: 0.42, pulse: 0.24,
    }),
    curious: state({
      bodyRotation: 2.7, bodySkew: 0.7, morph: -0.07, eyeScaleX: 1.035,
      eyeScaleY: 0.96, pupilFocus: 0.62, gazeInfluence: 0.92,
      accent: '#9a886f', glow: 0.14, rimIntensity: 0.32,
    }),
    confused: state({
      bodyRotation: 4.8, bodySkew: 1.5, morph: 0.17, eyeOpenL: 0.72,
      eyeOpenR: 0.9, eyeScaleY: 0.76, eyeSpacing: 1.25, pupilFocus: 0.5,
      gazeInfluence: 0.68, accent: '#a48b67', glow: 0.1, rimIntensity: 0.34,
      mouth: 0.78,
    }),
    bored: state({
      bodyScaleY: 0.98, bodyLift: -1, morph: 0.04, eyeOpenL: 0.52,
      eyeOpenR: 0.52, eyeScaleY: 0.7, pupilFocus: 0.24, gazeInfluence: 0.32,
      accent: '#9b907f', glow: 0.05, rimIntensity: 0.2,
    }),
    proud: state({
      bodyScaleX: 1.02, bodyScaleY: 1.03, bodyLift: 4, morph: -0.03,
      eyeScaleY: 0.76, faceOffsetY: -3, pupilFocus: 0.62, gazeInfluence: 0.7,
      accent: '#879a7e', glow: 0.18, rimIntensity: 0.44, pulse: 0.26, sparkle: 0.1,
    }),
    shy: state({
      bodyScaleX: 0.98, bodyScaleY: 0.98, bodyLift: -1, morph: 0.15,
      eyeOpenL: 0.62, eyeOpenR: 0.62, eyeScaleY: 0.68, eyeSpacing: 0.8,
      pupilFocus: 0.34, gazeInfluence: 0.42, accent: '#a18b71', glow: 0.08,
    }),
    sad: state({
      bodyScaleY: 0.97, bodyLift: -3, morph: -0.18, eyeOpenL: 0.62,
      eyeOpenR: 0.62, eyeScaleY: 0.78, faceOffsetY: 3, pupilFocus: 0.28,
      gazeInfluence: 0.38, accent: '#9b907f', glow: 0.04, rimIntensity: 0.17,
    }),
    laughing: state({
      bodyScaleX: 1.025, bodyScaleY: 1.04, bodyLift: 5, morph: 0.16,
      eyeOpenL: 0.38, eyeOpenR: 0.38, eyeScaleY: 0.46, pupilFocus: 0.38,
      gazeInfluence: 0.68, accent: '#879a7e', glow: 0.22, rimIntensity: 0.46,
      sparkle: 0.16, mouth: 1,
    }),
    scared: state({
      bodyScaleX: 0.96, bodyScaleY: 1.04, morph: -0.22, eyeOpenL: 0.86,
      eyeOpenR: 0.9, eyeScaleX: 0.9, eyeScaleY: 1.06, pupilFocus: 0.88,
      gazeInfluence: 0.84, accent: '#a48b67', glow: 0.16, rimIntensity: 0.4,
    }),
    playful: state({
      bodyScaleX: 1.035, bodyScaleY: 0.96, bodyLift: 4, morph: 0.2,
      bodyRotation: -2.2, eyeScaleX: 1.035, eyeScaleY: 0.84, pupilFocus: 0.48,
      gazeInfluence: 0.88, accent: '#879a7e', glow: 0.2, rimIntensity: 0.46, sparkle: 0.12,
    }),
    celebrate: state({
      bodyScaleX: 1.055, bodyScaleY: 1.075, bodyLift: 8, morph: 0.22,
      eyeScaleX: 1.05, eyeScaleY: 0.64, pupilFocus: 0.5, gazeInfluence: 0.8,
      accent: '#819775', glow: 0.34, rimIntensity: 0.62, pulse: 0.72, sparkle: 0.56,
      particleRate: 0.32,
    }),
    orbit: state({
      accent: '#7f9080', rimIntensity: 0.48, glow: 0.2, orbitOpacity: 0.56,
      orbitSpeed: 0.38, orbitTilt: -21, orbitThickness: 1.35, particleRate: 0.08,
    }),
    radar: state({
      eyeScaleX: 1.035, pupilFocus: 0.8, gazeInfluence: 0.5,
      accent: '#8d947d', rimIntensity: 0.56, glow: 0.22, orbitOpacity: 0.72,
      orbitSpeed: 0.92, orbitTilt: -28, orbitThickness: 1.2, pulse: 0.2,
    }),
    progress: state({
      accent: '#879a7e', rimIntensity: 0.5, glow: 0.18, orbitOpacity: 0.62,
      orbitSpeed: 0.52, orbitTilt: -14, orbitThickness: 1.5, particleRate: 0.18,
    }),
    spawning: state({
      bodyScaleX: 0.12, bodyScaleY: 0.12, bodyLift: 0, morph: -0.16,
      eyeOpenL: 0.04, eyeOpenR: 0.04, eyeScaleX: 0.18, eyeScaleY: 0.18,
      gazeInfluence: 0.16, accent: '#ad9678', rimIntensity: 0.72, glow: 0.7,
      orbitOpacity: 0.72, orbitSpeed: 0.65, orbitTilt: -24, orbitThickness: 1.8,
      particleRate: 0.38, particleLife: 1, sparkle: 0.36, pulse: 0.8,
    }),
    humming: state({
      eyeScaleY: 0.9, pupilFocus: 0.46, gazeInfluence: 0.72,
      accent: '#9a886f', rimIntensity: 0.32, glow: 0.12, orbitOpacity: 0.06,
      orbitSpeed: 0.16, pulse: 0.2,
    }),
    loading: state({
      eyeScaleX: 1.015, pupilFocus: 0.7, gazeInfluence: 0.5,
      accent: '#9a886f', rimIntensity: 0.54, glow: 0.18, orbitOpacity: 0.2,
      orbitSpeed: 0.58, orbitTilt: -10, pulse: 0.28,
    }),
    dictating: state({
      eyeScaleX: 1.035, pupilFocus: 0.72, gazeInfluence: 0.6,
      accent: '#a18b71', rimIntensity: 0.6, glow: 0.22, orbitOpacity: 0.12,
      orbitSpeed: 0.32, pulse: 0.5,
    }),
    writing: state({
      eyeScaleX: 1.025, pupilFocus: 0.68, gazeInfluence: 0.46,
      accent: '#7f9080', rimIntensity: 0.5, glow: 0.16, orbitOpacity: 0.32,
      orbitSpeed: 0.42, orbitTilt: -15, particleRate: 0.08,
    }),
    sending: state({
      bodyScaleX: 0.97, bodyScaleY: 0.96, bodyLift: 3, morph: -0.07,
      eyeScaleX: 1.015, pupilFocus: 0.76, gazeInfluence: 0.56,
      accent: '#9a886f', rimIntensity: 0.62, glow: 0.24, orbitOpacity: 0.38,
      orbitSpeed: 0.66, pulse: 0.68,
    }),
    receiving: state({
      bodyScaleX: 1.02, bodyScaleY: 1.01, bodyLift: 2, morph: 0.07,
      eyeScaleY: 0.86, pupilFocus: 0.52, gazeInfluence: 0.72,
      accent: '#879a7e', rimIntensity: 0.58, glow: 0.24, orbitOpacity: 0.12,
      pulse: 0.62, sparkle: 0.1,
    }),
    uploading: state({
      accent: '#8d947d', rimIntensity: 0.48, glow: 0.18, orbitOpacity: 0.46,
      orbitSpeed: 0.56, orbitTilt: -31, pulse: 0.34, particleRate: 0.14,
    }),
    notifying: state({
      accent: '#879a7e', rimIntensity: 0.58, glow: 0.22, orbitOpacity: 0.1,
      pulse: 0.66, sparkle: 0.34,
    }),
    alerting: state({
      bodyScaleX: 0.98, bodyScaleY: 1.02, morph: -0.09, eyeOpenL: 0.56,
      eyeOpenR: 0.6, eyeScaleY: 0.68, gazeInfluence: 0.52,
      accent: '#b87865', rimIntensity: 0.66, glow: 0.18, pulse: 0.8, warning: 0.7,
    }),
    dragging: state({
      bodyScaleX: 1.02, bodyScaleY: 0.98, bodyLift: 1, morph: 0.05,
      eyeScaleX: 1.02, pupilFocus: 0.76, gazeInfluence: 0.64,
      accent: '#9a886f', rimIntensity: 0.4, glow: 0.14, orbitOpacity: 0.08,
      orbitSpeed: 0.18,
    }),
    bouncing: state({
      bodyScaleX: 1.04, bodyScaleY: 0.88, bodyLift: 6, morph: 0.16,
      eyeScaleY: 0.76, pupilFocus: 0.5, gazeInfluence: 0.8,
      accent: '#879a7e', rimIntensity: 0.46, glow: 0.2, pulse: 0.42,
    }),
    'powering-down': state({
      bodyScaleX: 0.18, bodyScaleY: 0.18, bodyLift: 0, morph: -0.18,
      eyeOpenL: 0.06, eyeOpenR: 0.06, eyeScaleX: 0.18, eyeScaleY: 0.18,
      gazeInfluence: 0.08, accent: '#a18b71', rimIntensity: 0.7, glow: 0.54,
      orbitOpacity: 0.5, orbitSpeed: 0.72, orbitTilt: -25, orbitThickness: 1.8,
      pulse: 0.68, sparkle: 0.28,
    }),

    // Product-result states are short confirmations layered on the same rig.
    saved: state({ accent: '#879a7e', rimIntensity: 0.62, glow: 0.24, orbitOpacity: 0.1, pulse: 0.7, sparkle: 0.34 }),
    launched: state({ bodyScaleX: 1.02, bodyScaleY: 1.03, bodyLift: 4, morph: -0.03, eyeScaleY: 0.76, pupilFocus: 0.64, gazeInfluence: 0.7, accent: '#879a7e', rimIntensity: 0.48, glow: 0.2, pulse: 0.42, sparkle: 0.22 }),
    reply: state({ bodyScaleX: 1.01, bodyScaleY: 1.01, bodyLift: 2, morph: 0.05, eyeScaleY: 0.84, pupilFocus: 0.52, gazeInfluence: 0.76, accent: '#879a7e', rimIntensity: 0.52, glow: 0.2, pulse: 0.54, sparkle: 0.08 }),
    error: state({ bodyScaleX: 0.98, bodyScaleY: 1.02, morph: -0.1, eyeOpenL: 0.54, eyeOpenR: 0.6, eyeScaleY: 0.68, gazeInfluence: 0.52, accent: '#b87865', rimIntensity: 0.64, glow: 0.16, pulse: 0.78, warning: 0.72, mouth: 0.82 }),
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
