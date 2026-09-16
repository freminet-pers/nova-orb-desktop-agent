"""Scene policy for the unchanged upstream renderer.

The renderer owns the 39 visual states. This module owns when a state may be
requested, how scenes are prioritized, and where they return after a scene.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Beat:
    state: str
    ms: int = 1500
    trick: str = ''


@dataclass(frozen=True)
class SceneRule:
    priority: int
    interruptible: bool = True
    recovery: str = 'idle'


UPSTREAM_GROUPS = {
    'Lifecycle': ('sleeping', 'waking', 'idle', 'listening', 'thinking', 'searching', 'working'),
    'Reactions': ('excited', 'surprised', 'suspicious', 'angry', 'drowsy', 'happy', 'curious',
                  'confused', 'bored', 'proud', 'shy', 'sad', 'laughing', 'scared', 'playful', 'celebrate'),
    'Agent morphs': ('orbit', 'radar', 'progress'),
    'Product lifecycle': ('spawning', 'humming', 'loading', 'dictating', 'writing', 'sending', 'receiving',
                          'uploading', 'notifying', 'alerting', 'dragging', 'bouncing', 'powering-down'),
}
UPSTREAM_STATES = tuple(state for group in UPSTREAM_GROUPS.values() for state in group)

STATE_RULES = {state: SceneRule(0) for state in UPSTREAM_STATES}
STATE_RULES.update({
    'sleeping': SceneRule(90, interruptible=False, recovery='sleeping'),
    'waking': SceneRule(95, recovery='idle'),
    'listening': SceneRule(90, interruptible=False, recovery='idle'),
    'thinking': SceneRule(80, recovery='idle'),
    'searching': SceneRule(60, recovery='idle'),
    'working': SceneRule(60, recovery='idle'),
    'excited': SceneRule(45, recovery='idle'),
    'laughing': SceneRule(55, recovery='idle'),
    'scared': SceneRule(55, recovery='idle'),
    'celebrate': SceneRule(65, recovery='idle'),
    'orbit': SceneRule(70, recovery='idle'),
    'radar': SceneRule(70, recovery='idle'),
    'progress': SceneRule(70, recovery='idle'),
    'spawning': SceneRule(96, interruptible=False, recovery='idle'),
    'loading': SceneRule(85, interruptible=False, recovery='idle'),
    'dictating': SceneRule(90, interruptible=False, recovery='idle'),
    'writing': SceneRule(80, recovery='idle'),
    'sending': SceneRule(80, recovery='idle'),
    'receiving': SceneRule(70, recovery='idle'),
    'uploading': SceneRule(60, recovery='idle'),
    'notifying': SceneRule(60, recovery='idle'),
    'alerting': SceneRule(70, recovery='idle'),
    'dragging': SceneRule(92, interruptible=False, recovery='idle'),
    'bouncing': SceneRule(78, recovery='idle'),
    'powering-down': SceneRule(100, interruptible=False, recovery='idle'),
})


# Direct interactions outrank ambient/random expressions. A locked scene
# cannot be replaced by random idle work, while a direct user action may still
# request the next scene through Controller.scene(..., source="user").
SCENE_RULES = {
    'sleep': SceneRule(90, interruptible=False, recovery='sleeping'),
    'wake': SceneRule(95, recovery='idle'),
    'feed': SceneRule(86, interruptible=False, recovery='humming'),
    'treat': SceneRule(86, interruptible=False, recovery='humming'),
    'full': SceneRule(80, recovery='idle'),
    'pet': SceneRule(78, recovery='idle'),
    'tickle': SceneRule(78, recovery='idle'),
    'play': SceneRule(82, interruptible=False, recovery='idle'),
    'seek': SceneRule(72, interruptible=False, recovery='idle'),
    'found': SceneRule(74, recovery='idle'),
    'highfive': SceneRule(72, interruptible=False, recovery='idle'),
    'win': SceneRule(74, recovery='idle'),
    'game_timeout': SceneRule(70, recovery='idle'),
    'drag_bounce': SceneRule(78, recovery='idle'),
    'drag_sway': SceneRule(74, recovery='idle'),
    'drag_settle': SceneRule(72, recovery='idle'),
    'exit': SceneRule(100, interruptible=False, recovery='idle'),
    'entrance': SceneRule(96, interruptible=False, recovery='idle'),
    'reply': SceneRule(55, recovery='idle'),
    'saved': SceneRule(58, recovery='idle'),
    'launched': SceneRule(58, recovery='idle'),
    'error': SceneRule(60, recovery='idle'),
}


SCENES = {
    'idle': [Beat('idle', 900)],
    'listening': [Beat('listening', 1200)],
    'thinking': [Beat('thinking', 1600)],
    'loading': [Beat('loading', 1600)],
    'dictating': [Beat('dictating', 1400)],
    'writing': [Beat('writing', 1400)],
    'sending': [Beat('sending', 1400)],
    'dragging': [Beat('dragging', 1400)],
    'feed': [Beat('curious', 650), Beat('happy', 1800)],
    'treat': [Beat('receiving', 800), Beat('happy', 1800)],
    'full': [Beat('shy', 1800)],
    'cooldown': [Beat('idle', 900)],
    'pet': [Beat('happy', 2200)],
    'tickle': [Beat('laughing', 2200)],
    'play': [Beat('excited', 1000), Beat('playful', 2400)],
    'call': [Beat('curious', 1600)],
    'sleep': [Beat('drowsy', 1600), Beat('sleeping', 2400)],
    'wake': [Beat('waking', 1200), Beat('curious', 1400)],
    'praise': [Beat('shy', 1200), Beat('proud', 1900)],
    'comfort': [Beat('sad', 1000), Beat('happy', 1800)],
    'tease': [Beat('suspicious', 1500), Beat('confused', 1200)],
    'startled': [Beat('scared', 1000), Beat('curious', 1500)],
    'shake': [Beat('angry', 1200), Beat('bored', 1000)],
    'drop': [Beat('bouncing', 1000, 'bounce'), Beat('playful', 1500)],
    'seek': [Beat('radar', 1800), Beat('searching', 7000)],
    'found': [Beat('surprised', 800), Beat('proud', 1700)],
    'highfive': [Beat('progress', 1500)],
    'win': [Beat('celebrate', 2600)],
    'focus': [Beat('orbit', 2800), Beat('humming', 3000)],
    'lookup': [Beat('searching', 700), Beat('working', 1000)],
    'launched': [Beat('proud', 1800)],
    'missing': [Beat('confused', 2000)],
    'saved': [Beat('notifying', 1700)],
    'backup': [Beat('progress', 1200), Beat('notifying', 1400)],
    'export': [Beat('uploading', 1400), Beat('notifying', 1400)],
    'reply': [Beat('receiving', 650), Beat('happy', 1800)],
    'error': [Beat('alerting', 1700), Beat('confused', 1200)],
    'entrance': [Beat('spawning', 1800)],
    'exit': [Beat('powering-down', 900)],
    'food_cue': [Beat('curious', 1600)],
    'game_timeout': [Beat('bored', 1800)],
    # A bounce is reserved for a fast vertical release. Horizontal release
    # gets the original curious/playful sway; a gentle release settles softly.
    'drag_bounce': [Beat('curious', 700, 'bounce'), Beat('playful', 850), Beat('idle', 500)],
    'drag_sway': [Beat('curious', 650), Beat('playful', 950), Beat('idle', 500)],
    'drag_settle': [Beat('curious', 500), Beat('idle', 650)],
}

# Persistent phases are driven by actual work, never random expressions.
PHASES = {'idle': 'idle', 'recording': 'listening', 'speech': 'dictating',
          'recognizing': 'loading', 'model': 'thinking', 'typing': 'writing',
          'request': 'sending', 'drag': 'dragging',
          # Agent progress names are deliberately kept in the business layer;
          # the renderer only receives visual state names through this table.
          'planning': 'thinking', 'parsing': 'thinking', 'tool': 'working', 'working': 'working',
          'success': 'saved', 'failure': 'error', 'cancel': 'idle'}


def interaction_scene(kind, outcome):
    # A repeated touch is still a tactile acknowledgement even when the
    # numeric reward is on cooldown. Feeding/treating must show refusal and
    # never play the successful feeding jump.
    if kind == 'pet':
        return 'pet'
    if not outcome['accepted']:
        return 'full' if kind in ('feed', 'treat') and outcome['state']['fullness'] > 92 else 'cooldown'
    return kind if kind in SCENES else 'call'


def payload(scene):
    return [dict(state=b.state, ms=b.ms, trick=b.trick) for b in SCENES[scene]]


def scene_rule(scene):
    return SCENE_RULES.get(scene, SceneRule(60))


def scene_duration(scene):
    return sum(beat.ms for beat in SCENES.get(scene, ()))
