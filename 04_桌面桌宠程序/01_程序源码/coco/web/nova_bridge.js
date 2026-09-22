/* Stable window.coco adapter. It keeps QWebChannel events separate from the
 * renderer so a future desktop or robot host can reuse the same pose API. */
(function (global) {
  'use strict';

  const renderer = global.NovaRenderer;
  const svg = document.getElementById('nova');
  const call = (name, args) => {
    if (!renderer || typeof renderer[name] !== 'function') return undefined;
    return renderer[name].apply(renderer, args || []);
  };

  global.coco = {
    snapshot: () => call('snapshot'),
    states: () => call('states'),
    gazeSnapshot: () => call('gazeSnapshot'),
    renderSnapshot: () => call('renderSnapshot'),
    setState: state => call('setState', [state]),
    sequence: steps => call('sequence', [steps]),
    react: (state, trick = '', duration = 2600) => call('react', [state, trick, duration]),
    gaze: (x, y, width, height) => call('gaze', [x, y, width, height]),
    clearGaze: () => call('clearGaze'),
    dragRelease: (kind, strength) => call('dragRelease', [kind, strength]),
    enter: () => call('enter'),
    handoff_enter: (source, context) => call('handoff_enter', [source, context]),
  };

  function actionBridge(bridge, name) {
    if (bridge && typeof bridge.action === 'function') bridge.action(name);
  }

  function connectChannel() {
    if (!global.qt || !global.qt.webChannelTransport || typeof global.QWebChannel !== 'function') return;
    new global.QWebChannel(global.qt.webChannelTransport, channel => {
      const bridge = channel.objects.desktop;
      svg.addEventListener('pointerdown', event => {
        if (event.button !== 0) return;
        svg.setPointerCapture(event.pointerId);
        actionBridge(bridge, 'press');
      });
      svg.addEventListener('pointermove', event => {
        if (event.buttons & 1) actionBridge(bridge, 'move');
      });
      svg.addEventListener('pointerup', event => {
        if (event.button === 0) actionBridge(bridge, 'release');
      });
      svg.addEventListener('pointercancel', () => actionBridge(bridge, 'cancel'));
      svg.addEventListener('dblclick', () => actionBridge(bridge, 'settings'));
      document.addEventListener('contextmenu', event => {
        event.preventDefault();
        actionBridge(bridge, 'menu');
      });
      actionBridge(bridge, 'ready');
    });
  }

  connectChannel();
})(window);
