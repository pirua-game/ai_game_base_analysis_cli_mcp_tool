"""
gdep.profile
Engine/Framework-specific profile system.
- Engine base class filtering
- Automatic lifecycle entry point suggestions
- .gdep-profile.json read/write
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# ── Profile Data Model ──────────────────────────────────────

@dataclass
class EngineProfile:
    engine:               str          # "unity" | "cocos2dx" | "unreal" | "dotnet" | "cpp" | "custom"
    display_name:         str          # Display name for UI

    # Engine base classes (displayed separately in scan coupling)
    engine_base_classes:  list[str] = field(default_factory=list)

    # Classes to exclude entirely from scan (hidden from coupling results)
    filter_classes:       list[str] = field(default_factory=list)

    # Lifecycle methods (automatic entry point suggestions)
    lifecycle_methods:    list[str] = field(default_factory=list)

    # Additional user-defined base classes (per-project customization)
    custom_base_classes:  list[str] = field(default_factory=list)

    # Toggle engine class filtering
    filter_engine_classes: bool = True

    # Split engine/project display in scan results
    split_engine_project:  bool = True

    def all_base_classes(self) -> set[str]:
        """Returns the full set of classes used for filtering."""
        return set(self.engine_base_classes) | set(self.custom_base_classes)

    def is_engine_class(self, class_name: str) -> bool:
        """Checks if a class is an engine base class."""
        return class_name in self.all_base_classes()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> EngineProfile:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Built-in Profile Presets ──────────────────────────────────────

PROFILES: dict[str, EngineProfile] = {

    "unity": EngineProfile(
        engine="unity",
        display_name="Unity",
        engine_base_classes=[
            "MonoBehaviour", "ScriptableObject", "Object",
            "Component", "Behaviour", "Transform",
            "Collider", "Collider2D", "Rigidbody", "Rigidbody2D",
            "Renderer", "MeshRenderer", "SpriteRenderer",
            "Animator", "Animation", "AudioSource", "Camera",
            "Canvas", "CanvasGroup", "RectTransform",
            "EventTrigger", "Button", "Text", "Image",
            "InputField", "Slider", "Toggle", "Dropdown",
            "NetworkBehaviour", "NetworkManager",
        ],
        filter_classes=[
            "MonoBehaviour", "ScriptableObject", "Object",
        ],
        lifecycle_methods=[
            "Awake", "Start", "Update", "FixedUpdate", "LateUpdate",
            "OnEnable", "OnDisable", "OnDestroy",
            "OnCollisionEnter", "OnCollisionExit", "OnTriggerEnter",
            "OnTriggerExit", "OnBecameVisible", "OnBecameInvisible",
        ],
    ),

    "cocos2dx": EngineProfile(
        engine="cocos2dx",
        display_name="Cocos2d-x",
        engine_base_classes=[
            "Node", "Layer", "Scene", "Sprite", "Label", "Menu",
            "MenuItem", "MenuItemSprite", "MenuItemLabel",
            "Action", "Component", "Ref", "Object",
            "DrawNode", "RenderTexture", "ParticleSystem",
            "EventListener", "EventListenerTouch",
            "EventListenerKeyboard", "EventListenerMouse",
            "Touch", "Event", "Director",
            "TextureCache", "SpriteFrameCache",
            "LayerColor", "LayerGradient",
            "ScrollView", "ListView", "PageView",
            "Button", "CheckBox", "Slider", "TextField",
            "Scale9Sprite", "MotionStreak",
            "TransitionScene", "TransitionFade",
        ],
        filter_classes=[
            "Node", "Layer", "Scene", "Ref", "Object",
            "Director", "Action",
        ],
        lifecycle_methods=[
            "init", "onEnter", "onExit", "onEnterTransitionDidFinish",
            "onExitTransitionDidStart", "update", "draw",
            "visit", "cleanup",
        ],
    ),

    "unreal": EngineProfile(
        engine="unreal",
        display_name="Unreal Engine 5",
        engine_base_classes=[
            "AActor", "UObject", "UActorComponent",
            "USceneComponent", "APawn", "ACharacter",
            "AController", "APlayerController", "AAIController",
            "UGameInstance", "AGameMode", "AGameState",
            "UUserWidget", "UWidget", "UPanelWidget",
            "UAnimInstance", "UAnimNotify",
            "USoundBase", "UParticleSystem",
        ],
        filter_classes=[
            "AActor", "UObject", "UActorComponent",
        ],
        lifecycle_methods=[
            "BeginPlay", "Tick", "EndPlay",
            "BeginOverlap", "EndOverlap",
            "ReceiveHit", "PostInitializeComponents",
            "SetupPlayerInputComponent",
        ],
    ),

    "dotnet": EngineProfile(
        engine="dotnet",
        display_name=".NET",
        engine_base_classes=[
            "Object", "ValueType", "Enum", "Delegate",
            "Exception", "Attribute", "Stream",
            "TextWriter", "TextReader",
        ],
        filter_classes=["Object", "ValueType"],
        lifecycle_methods=[
            "Main", "Dispose", "Finalize",
            "OnStart", "OnStop", "OnPause", "OnResume",
        ],
    ),

    "cpp": EngineProfile(
        engine="cpp",
        display_name="C++ (Generic)",
        engine_base_classes=[],
        filter_classes=[],
        lifecycle_methods=["main", "init", "update", "render", "shutdown"],
    ),
}


# ── .gdep-profile.json Read/Write ─────────────────────────

PROFILE_FILENAME = ".gdep-profile.json"


def load_profile(project_path: str,
                 engine_hint: str | None = None) -> EngineProfile:
    """
    1. Returns .gdep-profile.json if it exists.
    2. Otherwise, returns a built-in preset based on engine_hint.
    3. If neither is available, returns the default C++ profile.
    """
    profile_path = Path(project_path) / PROFILE_FILENAME
    if profile_path.exists():
        try:
            data  = json.loads(profile_path.read_text(encoding="utf-8"))
            base  = PROFILES.get(data.get("engine", "cpp"), PROFILES["cpp"])
            # Override with saved custom values
            merged = EngineProfile(
                engine=data.get("engine", base.engine),
                display_name=data.get("display_name", base.display_name),
                engine_base_classes=data.get("engine_base_classes",
                                             base.engine_base_classes),
                filter_classes=data.get("filter_classes", base.filter_classes),
                lifecycle_methods=data.get("lifecycle_methods",
                                          base.lifecycle_methods),
                custom_base_classes=data.get("custom_base_classes", []),
                filter_engine_classes=data.get("filter_engine_classes", True),
                split_engine_project=data.get("split_engine_project", True),
            )
            return merged
        except Exception:
            pass

    # Return built-in preset based on engine_hint
    if engine_hint:
        key = _normalize_engine_key(engine_hint)
        if key in PROFILES:
            return PROFILES[key]

    return PROFILES.get("cpp", EngineProfile(
        engine="cpp", display_name="C++ (Generic)"
    ))


def save_profile(project_path: str, profile: EngineProfile) -> str:
    """Saves the profile to .gdep-profile.json and returns the path."""
    profile_path = Path(project_path) / PROFILE_FILENAME
    data = profile.to_dict()
    profile_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return str(profile_path)


def profile_from_detector(kind: str, engine: str | None) -> EngineProfile:
    """
    Returns a profile using the ProjectKind/engine string from the detector.
    Used for integration with detector.py.
    """
    if not engine:
        return PROFILES.get("cpp")

    key = _normalize_engine_key(engine)
    return PROFILES.get(key, PROFILES.get("cpp"))


def _normalize_engine_key(engine_str: str) -> str:
    s = engine_str.lower()
    if "unity"   in s: return "unity"
    if "cocos"   in s: return "cocos2dx"
    if "unreal"  in s: return "unreal"
    if "dotnet"  in s or ".net" in s: return "dotnet"
    return "cpp"


# ── Profile-based Filtering Utilities ─────────────────────────────────

def filter_coupling(coupling: list[dict],
                    profile: EngineProfile) -> tuple[list[dict], list[dict]]:
    """
    Splits the coupling list into project classes and engine classes.
    Returns: (project_classes, engine_classes)
    """
    if not profile.filter_engine_classes:
        return coupling, []

    engine_set  = profile.all_base_classes()
    project     = [c for c in coupling if c["name"] not in engine_set]
    engine      = [c for c in coupling if c["name"] in engine_set]
    return project, engine


def suggest_entry_points(class_methods: list[str],
                         profile: EngineProfile) -> list[str]:
    """
    Returns lifecycle entry point candidates from a class's method list.
    """
    lifecycle = set(profile.lifecycle_methods)
    return [m for m in class_methods if m in lifecycle]


def classify_class(class_name: str, bases: list[str],
                   profile: EngineProfile) -> str:
    """
    Classifies a class.
    Returns: "engine_base" | "engine_derived" | "project"
    """
    engine_set = profile.all_base_classes()
    if class_name in engine_set:
        return "engine_base"
    if any(b in engine_set for b in bases):
        return "engine_derived"
    return "project"
