"""
/api/engine  — 신규 분석 엔진 라우터
Unity Event / Animator / UE5 GAS / ABP / BT / StateTree
"""
from __future__ import annotations
import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

router = APIRouter()


# ── Unity Event 바인딩 ────────────────────────────────────────

class UnityEventsRequest(BaseModel):
    path:        str
    method_name: Optional[str] = None


@router.post("/unity/events")
def unity_events(req: UnityEventsRequest):
    try:
        from gdep.unity_event_refs import build_event_map, format_event_result
        from gdep.confidence import ConfidenceTier, confidence_footer
        event_map = build_event_map(req.path)
        result = format_event_result(event_map, req.method_name)
        result += confidence_footer(ConfidenceTier.HIGH, "UnityEvent source regex")
        return {"result": result}
    except Exception as e:
        return {"result": f"Error: {e}"}


# ── Unity Animator ────────────────────────────────────────────

class UnityAnimatorRequest(BaseModel):
    path:            str
    controller_name: Optional[str] = None


@router.post("/unity/animator")
def unity_animator(req: UnityAnimatorRequest):
    try:
        from gdep.unity_animator import analyze_animator, _find_controllers

        # Try given path first; if no controllers found, walk up to project root
        # (Web UI passes Scripts path, but .controller files live in Assets root)
        search_path = req.path
        controllers = _find_controllers(search_path, req.controller_name)

        if not controllers:
            # Walk up at most 3 levels (Scripts → Assets → ProjectRoot → ...)
            p = Path(req.path).resolve()
            for _ in range(3):
                p = p.parent
                if not p.exists():
                    break
                candidates = _find_controllers(str(p), req.controller_name)
                if candidates:
                    search_path = str(p)
                    break

        result = analyze_animator(search_path, req.controller_name)
        from gdep.confidence import ConfidenceTier, confidence_footer
        result += confidence_footer(ConfidenceTier.HIGH, ".controller YAML source parse")
        return {"result": result}
    except Exception as e:
        return {"result": f"Error: {e}"}


# ── UE5 GAS ──────────────────────────────────────────────────

class UE5GasRequest(BaseModel):
    path:         str
    class_name:   Optional[str] = None
    detail_level: str           = "summary"
    category:     Optional[str] = None
    query:        Optional[str] = None


@router.post("/ue5/gas")
def ue5_gas(req: UE5GasRequest):
    try:
        from gdep.ue5_gas_analyzer import analyze_gas
        result = analyze_gas(req.path, req.class_name, req.detail_level, req.category, req.query)
        return {"result": result}
    except Exception as e:
        return {"result": f"Error: {e}"}


@router.post("/ue5/gas/graph")
def ue5_gas_graph(req: UE5GasRequest):
    """GAS 연결 그래프를 JSON으로 반환 (ReactFlow 시각화용)"""
    try:
        from gdep.ue5_gas_analyzer import build_gas_report
        from pathlib import Path as _Path
        report = build_gas_report(req.path)

        nodes: list[dict] = []
        edges: list[dict] = []
        seen_nodes: set[str] = set()
        seen_edges: set[str] = set()

        def add_node(nid: str, label: str, ntype: str):
            if nid not in seen_nodes:
                seen_nodes.add(nid)
                nodes.append({"id": nid, "label": label, "type": ntype})

        def add_edge(src: str, tgt: str, rel: str):
            if src not in seen_nodes or tgt not in seen_nodes:
                return
            key = f"{src}→{tgt}"
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append({"from": src, "to": tgt, "relation": rel})

        # ── 1. C++ Ability 노드 ──────────────────────────────────
        for ga in report.abilities:
            add_node(f"ga_{ga.name}", ga.name, "ability")

        # ── 2. C++ Effect 노드 ──────────────────────────────────
        for ge in report.effects:
            add_node(f"ge_{ge.name}", ge.name, "effect")

        # ── 3. C++ AttributeSet 노드 ────────────────────────────
        for aset in report.attr_sets:
            add_node(f"as_{aset.name}", aset.name, "attribute_set")

        # ── 4. ASC 노드 (최대 3개) ───────────────────────────────
        for asc in report.asc_classes[:3]:
            add_node(f"asc_{asc}", asc, "ability")

        # ── 5. Blueprint 에셋 노드 (GA_*/GE_*/AS_*) ─────────────
        #  asset_refs에서 파일명 기준으로 BP 에셋 분류
        bp_ga_set: set[str] = set()
        bp_ge_set: set[str] = set()
        bp_as_set: set[str] = set()
        for asset in report.asset_refs:
            name = asset.asset_name
            if not name:
                name = _Path(asset.asset_path).stem
            if asset.has_ga and (name.startswith("GA_") or "Ability" in name):
                bp_ga_set.add(name)
            if asset.has_ge and (name.startswith("GE_") or name.startswith("GAS_GE") or "Effect" in name):
                bp_ge_set.add(name)
            if asset.has_as and name.startswith("AS_"):
                bp_as_set.add(name)
            # bp_refs로 참조된 에셋도 미리 등록
            bp_ga_set.update(asset.bp_ga_refs)
            bp_ge_set.update(asset.bp_ge_refs)
            bp_as_set.update(asset.bp_as_refs)

        for name in sorted(bp_ga_set)[:20]:
            add_node(f"bpga_{name}", name, "bp_ability")
        for name in sorted(bp_ge_set)[:20]:
            add_node(f"bpge_{name}", name, "bp_effect")
        for name in sorted(bp_as_set)[:10]:
            add_node(f"bpas_{name}", name, "bp_attr_set")

        # ── 6-pre. 룩업: C++ 클래스 → BP GA가 직접 참조하는 BP GE 목록 ──
        # class_refs로 BP GA가 어떤 C++ GA를 구현하는지 알 수 있고,
        # bp_ge_refs로 그 BP GA가 어떤 BP GE를 사용하는지 알 수 있음.
        # 이를 결합해 C++ GA → BP GE 직접 연결에 활용한다.
        cpp_cls_to_bp_ge_refs: dict[str, list[str]] = {}
        for asset in report.asset_refs:
            bp_name = asset.asset_name or _Path(asset.asset_path).stem
            if bp_name not in bp_ga_set or not asset.bp_ge_refs:
                continue
            for cpp_cls in asset.class_refs:
                cpp_cls_to_bp_ge_refs.setdefault(cpp_cls, []).extend(asset.bp_ge_refs)

        # ── 6. 엣지: C++ GA → GE (BP 구현체 경유 직접 연결 우선) ────
        for ga in report.abilities:
            ga_nid = f"ga_{ga.name}"

            # 우선순위 1: BP GA 구현체의 bp_ge_refs 기반 직접 연결
            for ge_ref in cpp_cls_to_bp_ge_refs.get(ga.name, []):
                add_edge(ga_nid, f"bpge_{ge_ref}", "applies")

            # 우선순위 2: C++ UPROPERTY 변수명 → C++ GE 이름 키워드 매칭
            for ref_var in ga.ge_refs:
                rv_low = ref_var.lower()
                for ge in report.effects:
                    ge_low = ge.name.lower()
                    if rv_low in ge_low or ge_low in rv_low:
                        add_edge(ga_nid, f"ge_{ge.name}", "applies")

            # 우선순위 3: ge_refs 없고 BP 직접 연결도 없는 GA — 이름 유사도 fallback
            if not ga.ge_refs and ga.name not in cpp_cls_to_bp_ge_refs:
                ga_bare = ga.name.lower().replace("ability", "").replace("uarg", "").replace("uarr", "")
                for ge in report.effects:
                    ge_bare = ge.name.lower().replace("effect", "").replace("uge_", "")
                    if ga_bare and ge_bare and len(ga_bare) > 3 and (ga_bare in ge_bare or ge_bare in ga_bare):
                        add_edge(ga_nid, f"ge_{ge.name}", "applies")

        # ── 7. 엣지: Blueprint GA → Blueprint GE (bp_refs 직접 연결) ─
        for asset in report.asset_refs:
            src_name = asset.asset_name or _Path(asset.asset_path).stem
            src_nid  = f"bpga_{src_name}" if src_name in bp_ga_set else None
            if src_nid is None:
                continue
            for ge_ref in asset.bp_ge_refs:
                add_edge(src_nid, f"bpge_{ge_ref}", "applies")
            for as_ref in asset.bp_as_refs:
                add_edge(src_nid, f"bpas_{as_ref}", "uses_attr")

        # ── 8. 엣지: C++ GA → BP GA 연결 (class_refs 기반) ─────
        for asset in report.asset_refs:
            bp_name = asset.asset_name or _Path(asset.asset_path).stem
            if bp_name not in bp_ga_set:
                continue
            for cpp_cls in asset.class_refs:
                ga_nid = f"ga_{cpp_cls}"
                bp_nid = f"bpga_{bp_name}"
                add_edge(ga_nid, bp_nid, "bp_impl")

        # ── 9. 엣지: ASC → AttributeSet ─────────────────────────
        for aset in report.attr_sets:
            for asc in report.asc_classes[:3]:
                add_edge(f"asc_{asc}", f"as_{aset.name}", "owns")

        # ── 10. Tag 노드 (게임플레이 관련 상위 8개) ─────────────
        game_tags = [t for t in sorted(report.all_tags)
                     if any(t.startswith(p) for p in
                            ("Ability.", "Effect.", "Status.", "Event.", "Gameplay.", "GAS.", "Input."))
                     ][:8]
        for tag in game_tags:
            nid = f"tag_{tag.replace('.', '_')}"
            add_node(nid, tag, "tag")
            for ga in report.abilities:
                if tag in ga.tags:
                    add_edge(f"ga_{ga.name}", nid, "uses_tag")
            for bp_name in bp_ga_set:
                # Blueprint GA 이름에서 Ability 키워드 기반 tag 연결
                bare = bp_name.replace("GA_", "").lower()
                if bare and any(bare in t.lower() for t in ga.tags for ga in report.abilities):
                    add_edge(f"bpga_{bp_name}", nid, "uses_tag")

        return {
            "nodes": nodes,
            "edges": edges,
            "summary": {
                "abilities":    len(report.abilities),
                "effects":      len(report.effects),
                "attr_sets":    len(report.attr_sets),
                "tags":         len(report.all_tags),
                "bp_abilities": len(bp_ga_set),
                "bp_effects":   len(bp_ge_set),
            }
        }
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}


# ── UE5 Animation (ABP + Montage) ─────────────────────────────

class UE5AnimationRequest(BaseModel):
    path:         str
    asset_name:   Optional[str] = None
    asset_type:   str = "all"
    detail_level: str = "summary"


@router.post("/ue5/animation")
def ue5_animation(req: UE5AnimationRequest):
    try:
        from gdep.ue5_animator import analyze_abp, analyze_montage

        def _trim_summary(text: str) -> str:
            out, skip = [], False
            for line in text.splitlines():
                if line.startswith("###"):
                    skip = not any(k in line for k in [
                        "States", "Animation Slots", "GAS-related",
                        "Sections", "Slots", "Referenced Anim"
                    ])
                if not skip:
                    out.append(line)
            return "\n".join(out)

        if req.asset_type == "abp":
            raw = analyze_abp(req.path, req.asset_name)
        elif req.asset_type == "montage":
            raw = analyze_montage(req.path, req.asset_name)
        else:
            abp_result  = analyze_abp(req.path, req.asset_name)
            mont_result = analyze_montage(req.path, req.asset_name)
            # 둘 다 LFS fallback이면 통합 fallback 한 번만 표시
            if "⚠️ Git LFS" in abp_result and "⚠️ Git LFS" in mont_result:
                from gdep.ue5_animator import _lfs_fallback_anim
                raw = _lfs_fallback_anim(req.path, 'all')
            else:
                raw = abp_result + "\n\n" + mont_result

        result = raw if req.detail_level == "full" else _trim_summary(raw)
        return {"result": result}
    except Exception as e:
        return {"result": f"Error: {e}"}


# ── UE5 BehaviorTree ──────────────────────────────────────────

class UE5AIRequest(BaseModel):
    path:       str
    asset_name: Optional[str] = None


@router.post("/ue5/behavior_tree")
def ue5_behavior_tree(req: UE5AIRequest):
    try:
        from gdep.ue5_ai_analyzer import analyze_behavior_tree
        result = analyze_behavior_tree(req.path, req.asset_name)
        return {"result": result}
    except Exception as e:
        return {"result": f"Error: {e}"}


# ── UE5 StateTree ─────────────────────────────────────────────

@router.post("/ue5/state_tree")
def ue5_state_tree(req: UE5AIRequest):
    try:
        from gdep.ue5_ai_analyzer import analyze_state_tree
        result = analyze_state_tree(req.path, req.asset_name)
        return {"result": result}
    except Exception as e:
        return {"result": f"Error: {e}"}


# ── Axmol ─────────────────────────────────────────────────────

class AxmolEventsRequest(BaseModel):
    path:        str
    method_name: str | None = None


@router.post("/axmol/events")
def axmol_events(req: AxmolEventsRequest):
    try:
        from gdep.axmol_event_refs import build_event_map, format_event_result
        event_map = build_event_map(req.path)
        result = format_event_result(event_map, req.method_name)
        return {"result": result}
    except Exception as e:
        return {"result": f"Error: {e}"}
