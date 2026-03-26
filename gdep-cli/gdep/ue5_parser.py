"""
gdep.ue5_parser
UE5 C++ source parser.

Updates:
  - UPROPERTY meta=(…) nested parenthesis handling (balanced paren extraction)
  - Enhanced parsing for standard functions without UFUNCTION (const override, virtual, etc.)
  - TObjectPtr<T>, TSubclassOf<T> normalization
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Ignored Directories ──────────────────────────────────────
_IGNORE_DIRS = {
    "Binaries", "Intermediate", "Saved", "DerivedDataCache",
    "Build", "Content", "Plugins", ".vs", ".idea",
    "ThirdParty", "External",
}

# ── UE5 Lifecycle Methods ────────────────────────────────────
UE5_LIFECYCLE = {
    "BeginPlay", "EndPlay", "Tick", "PostInitializeComponents",
    "BeginDestroy", "PostLoad", "PreInitializeComponents",
    "OnConstruction", "PostActorCreated", "Destroyed",
    "InitializeComponent", "UninitializeComponent",
    "OnRegister", "OnUnregister",
    "ActivateAbility", "EndAbility", "CancelAbility",
    "CommitAbility", "CanActivateAbility",
    "PostGameplayEffectExecute", "PreAttributeChange", "PostAttributeChange",
    "SetupPlayerInputComponent", "PossessedBy", "UnPossessed", "OnRep_PlayerState",
    "NativeConstruct", "NativeDestruct", "NativeTick", "NativeOnInitialized",
}

# ── UE5 Engine Base Classes ──────────────────────────────────
UE5_ENGINE_BASES = {
    "UObject","AActor","APawn","ACharacter","AController",
    "APlayerController","AAIController","AGameMode","AGameModeBase",
    "AGameState","AGameStateBase","APlayerState","AHUD",
    "UActorComponent","USceneComponent","UPrimitiveComponent",
    "UMeshComponent","USkeletalMeshComponent","UStaticMeshComponent",
    "UCapsuleComponent","USphereComponent","UBoxComponent",
    "UGameInstance","ULocalPlayer",
    "UGameplayAbility","UAttributeSet","UAbilitySystemComponent",
    "UGameplayEffect","UGameplayTask",
    "UUserWidget","UWidget","UCanvasPanel",
    "IAbilitySystemInterface","IInterface",
}

# ── Basic Types to Ignore during Dependency Analysis ──────────
UE5_BASIC_TYPES = {
    "int", "int32", "uint32", "int64", "uint64", "float", "double", "bool", "void",
    "FVector", "FRotator", "FQuat", "FTransform", "FString", "FName", "FText",
    "FColor", "FLinearColor", "FIntPoint", "FGuid", "FDateTime", "FTimespan",
    "FVector2D", "FTimerHandle", "TObjectPtr", "TSubclassOf", "TArray", "TMap", "TSet",
    # ue5_ts_parser._clean_macros placeholders — must never count as real deps
    "UE5TemplateType", "UE5TemplateArg",
    "TWeakObjectPtr", "TSharedPtr", "TSharedRef",
    "uint8", "int8", "uint16", "int16", "long", "short", "char", "size_t",
    "UClass", "UStruct", "UObject", "AActor",
}


# ── Data Classes ─────────────────────────────────────────────

@dataclass
class UE5Property:
    name:          str
    type_:         str
    specifiers:    list[str] = field(default_factory=list)
    category:      str       = ""
    access:        str       = "public"
    is_replicated: bool      = False


@dataclass
class UE5Function:
    name:         str
    return_type:  str       = "void"
    params:       list[str] = field(default_factory=list)
    specifiers:   list[str] = field(default_factory=list)
    access:       str       = "public"
    is_lifecycle: bool      = False
    is_override:  bool      = False
    is_virtual:   bool      = False
    body_text:    str       = ""  # For linter/deep analysis
    source_file:  str       = ""  # For reporting


@dataclass
class UE5Class:
    name:         str
    kind:         str
    bases:        list[str]         = field(default_factory=list)
    specifiers:   list[str]         = field(default_factory=list)
    properties:   list[UE5Property] = field(default_factory=list)
    functions:    list[UE5Function] = field(default_factory=list)
    dependencies: list[str]         = field(default_factory=list) # For --deep mode
    enum_values:  list[str]         = field(default_factory=list)
    source_file:  str               = ""
    module_api:   str               = ""


@dataclass
class UE5Project:
    root:    Path
    classes: dict[str, UE5Class] = field(default_factory=dict)
    structs: dict[str, UE5Class] = field(default_factory=dict)
    enums:   dict[str, UE5Class] = field(default_factory=dict)


# ── Balanced Parenthesis Extraction ──────────────────────────

def _extract_balanced(text: str, start: int) -> tuple[str, int]:
    """
    Assumes text[start] is '(', returns content up to the matching ')'.
    return: (inner content, position after closing parenthesis)
    """
    assert text[start] == '(', f"Expected '(' at pos {start}, got '{text[start]}'"
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return text[start+1:i], i + 1
    return text[start+1:], len(text)


def _find_macro_paren(text: str, pos: int, macro: str) -> tuple[str, int] | None:
    """
    Finds macro + '(' after pos and extracts balanced parenthesis.
    return: (inner content, position after closing parenthesis) or None
    """
    idx = text.find(macro, pos)
    if idx == -1:
        return None
    # Skip whitespace after macro
    j = idx + len(macro)
    while j < len(text) and text[j] in ' \t\n':
        j += 1
    if j >= len(text) or text[j] != '(':
        return None
    inner, end = _extract_balanced(text, j)
    return inner, end


# ── Specifier Parsing ─────────────────────────────────────────

def _parse_specifiers(raw: str) -> tuple[list[str], str]:
    """'EditAnywhere, Category="Foo", meta=(...)' → (['EditAnywhere'], 'Foo')"""
    specs = []
    cat   = ""
    # Remove meta=(...)
    raw = re.sub(r'meta\s*=\s*\([^)]*\)', '', raw, flags=re.DOTALL)
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        cm = re.match(r'Category\s*=\s*["\']([^"\'|]+)', part, re.IGNORECASE)
        if cm:
            cat = cm.group(1).strip()
            continue
        if '=' in part:
            part = part.split('=')[0].strip()
        if part and re.match(r'^[A-Za-z_]\w*$', part):
            specs.append(part)
    return specs, cat


def _normalize_type(t: str) -> str:
    t = t.strip()
    # 1. Remove 'class ', 'struct ' prefixes
    t = re.sub(r'^(class|struct|enum)\s+', '', t)

    # 2. Extract inner type from templates like TObjectPtr<T>, TSubclassOf<T>, TArray<T>, TMap<K, V>
    m = re.search(r'<(.*)>', t)
    if m:
        inner = m.group(1).split(',')[0].strip() # Take only the first argument for TMap
        return _normalize_type(inner) # Recursive call for nested types like TObjectPtr<A*>

    # 3. Remove const, pointer, and reference symbols
    t = re.sub(r'\bconst\b', '', t).strip()
    t = t.replace('*', '').replace('&', '').strip()

    # 4. Remove namespaces
    t = t.split('::')[-1].strip()

    return t


def _extract_bases(raw: str) -> list[str]:
    bases = []
    for part in raw.split(','):
        part = re.sub(r'\b(public|protected|private|virtual)\b', '', part).strip()
        part = re.sub(r'<[^>]+>', '', part).strip()
        if part and re.match(r'^[A-Za-z_]\w*$', part):
            bases.append(part)
    return bases


# ── Access Section Map ────────────────────────────────────────

_ACCESS_PAT = re.compile(r'(?m)^[ \t]*(public|protected|private)\s*:')

def _build_access_map(body: str) -> list[tuple[int, str]]:
    sections: list[tuple[int, str]] = [(0, "public")]
    for m in _ACCESS_PAT.finditer(body):
        sections.append((m.start(), m.group(1)))
    return sections

def _get_access(offset: int, sections: list[tuple[int, str]]) -> str:
    cur = "public"
    for pos, acc in sections:
        if pos <= offset:
            cur = acc
        else:
            break
    return cur


# ── Function Parsing ──────────────────────────────────────────

# Match function declarations on a single line (up to semicolon)
# Access specifiers (public:) are removed before application, so DOTALL is not required.
_FUNC_PAT = re.compile(
    r'^[ \t]*'
    r'(virtual\s+|static\s+|inline\s+|explicit\s+|FORCEINLINE\s+)*'  # Prefix keywords
    r'([\w:<>\*&]+(?:\s*\*)?)\s+'    # Return type (single token + pointer)
    r'(\w+)\s*'                       # Function name
    r'\(([^)]*)\)'                    # Parameters
    r'(?:\s+const)?'
    r'(?:\s+override)?'
    r'(?:\s+final)?'
    r'(?:\s*=\s*0)?'
    r'\s*;',
    re.MULTILINE,
)

_BAD_FUNC_NAMES = {
    "if","for","while","switch","return","delete","new",
    "sizeof","decltype","static_assert","GENERATED_BODY",
    "UFUNCTION","UPROPERTY","UCLASS","USTRUCT","DECLARE",
    "check","ensure","verify","checkf","ensureMsgf",
}

def _parse_functions(body: str, access_map: list[tuple[int, str]]) -> list[UE5Function]:
    results: list[UE5Function] = []
    seen: set[str] = set()

    # Remove access specifier lines to prevent them from mixing with return types
    clean_body = re.sub(r'(?m)^[ \t]*(public|protected|private)\s*:[ \t]*$', '', body)

    # Collect UFUNCTION positions (based on original body)
    uf_by_end: dict[int, list[str]] = {}
    pos = 0
    while True:
        r = _find_macro_paren(body, pos, "UFUNCTION")
        if r is None:
            break
        inner, end = r
        specs, _ = _parse_specifiers(inner)
        uf_by_end[end] = specs
        pos = end

    # Functions with UFUNCTION
    for uf_end, uf_specs in uf_by_end.items():
        snippet = clean_body[uf_end:uf_end + 400]
        fm = _FUNC_PAT.search(snippet)
        if not fm:
            continue
        fname = fm.group(3)   # group(3) = function name (new pattern)
        if fname in _BAD_FUNC_NAMES:
            continue
        ret    = _normalize_type(fm.group(2))
        params = [p.strip() for p in fm.group(4).split(',') if p.strip()]
        abs_off = uf_end + fm.start()
        access  = _get_access(abs_off, access_map)
        raw_decl = fm.group(0)
        results.append(UE5Function(
            name=fname, return_type=ret, params=params,
            specifiers=uf_specs, access=access,
            is_lifecycle=fname in UE5_LIFECYCLE,
            is_virtual='virtual' in raw_decl,
            is_override='override' in raw_decl,
        ))
        seen.add(fname)

    # Standard functions without UFUNCTION
    for fm in _FUNC_PAT.finditer(clean_body):
        fname = fm.group(3)
        if fname in seen or fname in _BAD_FUNC_NAMES:
            continue
        ret    = _normalize_type(fm.group(2))
        params = [p.strip() for p in fm.group(4).split(',') if p.strip()]
        access  = _get_access(fm.start(), access_map)
        raw_decl = fm.group(0)
        results.append(UE5Function(
            name=fname, return_type=ret, params=params,
            access=access,
            is_lifecycle=fname in UE5_LIFECYCLE,
            is_virtual='virtual' in raw_decl,
            is_override='override' in raw_decl,
        ))
        seen.add(fname)

    # Constructor / Destructor (no return type)
    ctor_pat = re.compile(
        r'^[ \t]*(?:explicit\s+)?([A-Z]\w+)\s*\([^)]*\)\s*;',
        re.MULTILINE,
    )
    dtor_pat = re.compile(
        r'^[ \t]*virtual\s+~(\w+)\s*\([^)]*\)\s*(?:override\s*)?;',
        re.MULTILINE,
    )
    for cm in ctor_pat.finditer(clean_body):
        fname = cm.group(1)
        if fname in seen or fname in _BAD_FUNC_NAMES: continue
        # Exclude macro keywords
        if fname in ('UCLASS','USTRUCT','UENUM','UFUNCTION','UPROPERTY'): continue
        access = _get_access(cm.start(), access_map)
        results.append(UE5Function(
            name=fname, return_type="", params=[],
            access=access, is_lifecycle=False,
        ))
        seen.add(fname)
    for dm in dtor_pat.finditer(clean_body):
        fname = f"~{dm.group(1)}"
        if fname in seen: continue
        access = _get_access(dm.start(), access_map)
        results.append(UE5Function(
            name=fname, return_type="", params=[],
            access=access, is_lifecycle=False, is_virtual=True,
        ))
        seen.add(fname)

    return results


# ── UPROPERTY Parsing ─────────────────────────────────────────

# Pattern for type + name following UPROPERTY
_PROP_TYPE_NAME = re.compile(
    r'\s*'
    r'((?:[\w:<>*&,\s]|TObjectPtr<[^>]+>|TSubclassOf<[^>]+>|TArray<[^>]+>)+?)\s+'
    r'(\w+)\s*;',
    re.DOTALL,
)

def _parse_properties(body: str, access_map: list[tuple[int, str]]) -> list[UE5Property]:
    results: list[UE5Property] = []
    seen: set[str] = set()
    pos = 0

    while True:
        r = _find_macro_paren(body, pos, "UPROPERTY")
        if r is None:
            break
        inner, end = r

        specs, cat = _parse_specifiers(inner)
        is_repl = any(s in ("Replicated", "ReplicatedUsing") for s in specs)

        # Extract type + name
        tm = _PROP_TYPE_NAME.match(body, end)
        if not tm:
            pos = end
            continue

        type_raw  = tm.group(1).strip()
        prop_name = tm.group(2)
        if prop_name in _BAD_FUNC_NAMES or prop_name == "GENERATED_BODY":
            pos = tm.end()
            continue

        type_norm = _normalize_type(type_raw)
        access    = _get_access(end, access_map)

        if prop_name not in seen:
            results.append(UE5Property(
                name=prop_name, type_=type_norm,
                specifiers=specs, category=cat,
                access=access, is_replicated=is_repl,
            ))
            seen.add(prop_name)

        pos = tm.end()

    return results


# ── UENUM Parsing ─────────────────────────────────────────────

_ENUM_PAT = re.compile(
    r'enum\s+(?:class\s+)?(\w+)\s*(?::\s*\w+)?\s*\{([^}]*)\}',
    re.DOTALL,
)

def _parse_enum(body: str, spec_raw: str) -> list[str]:
    vals = []
    for part in body.split(','):
        v = re.sub(r'UMETA\s*\([^)]*\)', '', part)
        v = re.sub(r'//[^\n]*', '', v).strip()
        v = v.split('=')[0].strip()
        if v and re.match(r'^[A-Za-z_]\w*$', v):
            vals.append(v)
    return vals


# ── Class Declaration Patterns ────────────────────────────────

_CLASS_DECL_PAT = re.compile(
    r'(?:class|struct)\s+'
    r'(?:(\w+_API)\s+)?'   # e.g., MYGAME_API
    r'(\w+)'               # Class name
    r'(?:\s*:\s*([^{;]+?))?'  # Inheritance
    r'\s*\{',
    re.DOTALL,
)

_MACRO_START = re.compile(r'\b(UCLASS|USTRUCT|UENUM)\s*\(')


# ── File Parsing ──────────────────────────────────────────────

def _parse_file(path: Path) -> list[UE5Class]:
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return []

    results: list[UE5Class] = []
    pos = 0
    n   = len(text)

    while pos < n:
        m = _MACRO_START.search(text, pos)
        if not m:
            break

        macro_kind = m.group(1)
        paren_start = text.index('(', m.start())
        inner, macro_end = _extract_balanced(text, paren_start)
        specifiers, _ = _parse_specifiers(inner)

        # ── UENUM ──
        if macro_kind == "UENUM":
            em = _ENUM_PAT.search(text, macro_end, macro_end + 1000)
            if em:
                enum_name = em.group(1)
                vals = _parse_enum(em.group(2), inner)
                results.append(UE5Class(
                    name=enum_name, kind="enum",
                    specifiers=specifiers, enum_values=vals,
                    source_file=str(path),
                ))
                pos = em.end()
            else:
                pos = macro_end
            continue

        # ── UCLASS / USTRUCT ──
        dm = _CLASS_DECL_PAT.search(text, macro_end, macro_end + 400)
        if not dm:
            pos = macro_end
            continue

        module_api = dm.group(1) or ""
        cls_name   = dm.group(2)
        bases_raw  = dm.group(3) or ""
        bases      = _extract_bases(bases_raw)
        kind       = "struct" if macro_kind == "USTRUCT" else "class"

        # Extract class body
        brace_start = text.index('{', dm.start())
        depth = 0
        brace_end = brace_start
        for i in range(brace_start, min(brace_start + 200_000, n)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    brace_end = i
                    break

        body       = text[brace_start + 1:brace_end]
        access_map = _build_access_map(body)

        cls = UE5Class(
            name=cls_name, kind=kind, bases=bases,
            specifiers=specifiers, module_api=module_api,
            source_file=str(path),
            properties=_parse_properties(body, access_map),
            functions=_parse_functions(body, access_map),
        )
        results.append(cls)
        pos = brace_end + 1

    return results


# ── Project Parsing ───────────────────────────────────────────

def parse_project(source_path: str) -> UE5Project:
    root = Path(source_path)
    proj = UE5Project(root=root)

    for h in root.rglob("*.h"):
        if any(p in _IGNORE_DIRS for p in h.parts):
            continue
        for cls in _parse_file(h):
            if cls.kind == "enum":
                proj.enums[cls.name]   = cls
            elif cls.kind == "struct":
                proj.structs[cls.name] = cls
            else:
                proj.classes[cls.name] = cls

    return proj


# ── Analysis Utilities ───────────────────────────────────────

def compute_coupling(proj: UE5Project) -> list[dict]:
    all_cls = {**proj.classes, **proj.structs}
    counts: dict[str, int] = {}

    for cls in all_cls.values():
        # 1. Inheritance-based dependencies
        for b in cls.bases:
            t = _normalize_type(b)
            if t and t not in UE5_BASIC_TYPES:
                counts[t] = counts.get(t, 0) + 1

        # 2. Property-based dependencies
        for p in cls.properties:
            t = _normalize_type(p.type_)
            if t and t not in UE5_BASIC_TYPES:
                counts[t] = counts.get(t, 0) + 1

        # 3. Behavioral dependencies based on --deep analysis
        for d in cls.dependencies:
            t = _normalize_type(d)
            if t and t not in UE5_BASIC_TYPES:
                counts[t] = counts.get(t, 0) + 1

    result = []
    # Remove self-dependencies and rank items; exclude engine/external types
    for name, score in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        if name not in all_cls:   # 프로젝트 외부 타입(엔진 API 등) 제외
            continue
        cls = all_cls.get(name)
        file_name = Path(cls.source_file).name if cls else "External / Engine"
        full_path = cls.source_file if cls else ""

        result.append({
            "name": name,
            "score": score,
            "file": file_name,
            "full_path": full_path
        })
    return result


def find_cycles(proj: UE5Project) -> list[str]:
    all_cls = {**proj.classes, **proj.structs}
    cycles: list[str] = []
    def dfs(name: str, path: list[str], visited: set[str]):
        if name in path:
            idx = path.index(name)
            cycles.append(" → ".join(path[idx:] + [name]))
            return
        if name in visited or name not in all_cls:
            return
        visited.add(name)
        for b in all_cls[name].bases:
            dfs(b, path + [name], visited)
    for name in list(all_cls.keys()):
        dfs(name, [], set())
    return list(dict.fromkeys(cycles))


def to_class_map(proj: UE5Project) -> dict:
    result = {}
    for name, cls in {**proj.classes, **proj.structs, **proj.enums}.items():
        result[name] = {
            "kind":   cls.kind,
            "bases":  cls.bases,
            "fields": [
                {
                    "name":       p.name,
                    "type":       p.type_,
                    "access":     p.access,
                    "specifiers": p.specifiers,
                    "category":   p.category,
                    "replicated": p.is_replicated,
                }
                for p in cls.properties
            ],
            "methods": [
                {
                    "name":        f.name,
                    "ret":         f.return_type,
                    "params":      f.params,
                    "isAsync":     False,
                    "access":      f.access,
                    "specifiers":  f.specifiers,
                    "isLifecycle": f.is_lifecycle,
                    "isOverride":  f.is_override,
                    "isVirtual":   f.is_virtual,
                }
                for f in cls.functions
            ],
            "ue_specifiers": cls.specifiers,
            "module_api":    cls.module_api,
            "enum_values":   cls.enum_values,
        }
    return result
