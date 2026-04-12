"""
/api/wiki  — 위키 브라우저 API
list / search / node / edges / graph / stats 엔드포인트
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from gdep.wiki.store import WikiStore
from gdep.wiki.models import WikiNode
from gdep.wiki.staleness import build_class_fingerprint_map, is_node_stale, get_project_fingerprint

router = APIRouter()


# ── Pydantic 응답 모델 ────────────────────────────────────────

class WikiNodeResponse(BaseModel):
    id: str
    type: str
    title: str
    file_path: str
    created_at: str
    updated_at: str
    stale: bool
    meta: dict


class WikiSearchResultResponse(BaseModel):
    node: WikiNodeResponse
    snippet: str
    score: float


class WikiGraphNode(BaseModel):
    id: str
    label: str
    type: str
    stale: bool


class WikiGraphEdge(BaseModel):
    source: str
    target: str
    relation: str


class WikiGraphData(BaseModel):
    nodes: list[WikiGraphNode]
    edges: list[WikiGraphEdge]


class WikiStatsResponse(BaseModel):
    types: dict[str, int]
    total_nodes: int
    total_edges: int
    stale_count: int


# ── 헬퍼 ─────────────────────────────────────────────────────

def _get_store(path: str) -> WikiStore:
    try:
        return WikiStore(path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Wiki store init failed: {e}")


def _node_to_response(node: WikiNode) -> WikiNodeResponse:
    return WikiNodeResponse(
        id=node.id,
        type=node.type,
        title=node.title,
        file_path=node.file_path,
        created_at=node.created_at,
        updated_at=node.updated_at,
        stale=node.stale,
        meta=node.meta or {},
    )


def _is_node_stale_live(node: WikiNode, path: str,
                         class_fp_map: dict[str, str],
                         project_fp_cache: list[str]) -> bool:
    """live staleness 계산 (wiki_list.py 로직 재사용)."""
    if node.type == "conversation":
        return False
    if node.type == "class":
        current = class_fp_map.get(node.title.lower())
        if current is None:
            if not project_fp_cache:
                project_fp_cache.append(get_project_fingerprint(path))
            current = project_fp_cache[0]
        return is_node_stale(node.source_fingerprint, current)
    if not project_fp_cache:
        project_fp_cache.append(get_project_fingerprint(path))
    return is_node_stale(node.source_fingerprint, project_fp_cache[0])


# ── 엔드포인트 ────────────────────────────────────────────────

@router.get("/stats", response_model=WikiStatsResponse)
def wiki_stats(path: str = Query(..., description="프로젝트 경로")):
    """위키 통계: 타입별 노드 수, 전체 엣지 수, stale 노드 수."""
    store = _get_store(path)
    try:
        conn = store._get_conn()

        # 타입별 카운트
        rows = conn.execute(
            "SELECT type, COUNT(*) as cnt FROM wiki_nodes GROUP BY type"
        ).fetchall()
        types = {r["type"]: r["cnt"] for r in rows}
        total_nodes = sum(types.values())

        # 엣지 수
        total_edges = conn.execute("SELECT COUNT(*) FROM wiki_edges").fetchone()[0]

        # stale 수 (live 계산)
        all_nodes = store.list_nodes(limit=1000)
        has_class = any(n.type == "class" for n in all_nodes)
        class_fp_map = build_class_fingerprint_map(path) if has_class else {}
        project_fp_cache: list[str] = []
        stale_count = sum(
            1 for n in all_nodes
            if _is_node_stale_live(n, path, class_fp_map, project_fp_cache)
        )

        return WikiStatsResponse(
            types=types,
            total_nodes=total_nodes,
            total_edges=total_edges,
            stale_count=stale_count,
        )
    finally:
        store.close()


@router.get("/list", response_model=list[WikiNodeResponse])
def wiki_list(
    path: str = Query(...),
    type: Optional[str] = Query(None, description="class|asset|system|pattern|conversation"),
    limit: int = Query(200),
):
    """타입별 노드 목록 반환 (live staleness 계산 포함)."""
    store = _get_store(path)
    try:
        nodes = store.list_nodes(node_type=type or None, limit=limit)

        has_class = any(n.type == "class" for n in nodes)
        class_fp_map = build_class_fingerprint_map(path) if has_class else {}
        project_fp_cache: list[str] = []

        result = []
        for node in nodes:
            stale_live = _is_node_stale_live(node, path, class_fp_map, project_fp_cache)
            resp = _node_to_response(node)
            resp.stale = stale_live
            result.append(resp)

        # updated_at 내림차순 정렬
        result.sort(key=lambda n: n.updated_at, reverse=True)
        return result
    finally:
        store.close()


@router.get("/search", response_model=list[WikiSearchResultResponse])
def wiki_search(
    path: str = Query(...),
    q: str = Query(..., description="검색 쿼리"),
    mode: str = Query("or", description="or|and|phrase"),
    type: Optional[str] = Query(None),
    related: bool = Query(False),
    limit: int = Query(20),
):
    """FTS5 BM25 + LIKE fallback 검색."""
    store = _get_store(path)
    try:
        results = store.search(
            query=q,
            node_type=type or None,
            related=related,
            limit=limit,
            mode=mode,
        )
        out = []
        for node, snippet, score in results:
            if not node.file_path:
                # stub 노드 (미분석 관계 노드) 포함
                pass
            out.append(WikiSearchResultResponse(
                node=_node_to_response(node),
                snippet=snippet,
                score=abs(score) if score not in (0.0, -1.0) else score,
            ))
        return out
    finally:
        store.close()


@router.get("/node")
def wiki_node(
    path: str = Query(...),
    node_id: str = Query(..., description="노드 ID (예: class:ZombieCharacter)"),
):
    """노드 상세 정보 + 마크다운 본문 반환."""
    store = _get_store(path)
    try:
        node = store.get(node_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
        content = store.read_content(node)
        return {
            "node": _node_to_response(node),
            "content": content,
        }
    finally:
        store.close()


@router.get("/edges", response_model=list[WikiGraphEdge])
def wiki_edges(
    path: str = Query(...),
    node_id: str = Query(...),
    relation: Optional[str] = Query(None),
    depth: int = Query(1, ge=1, le=3),
):
    """노드의 관계 엣지 목록 반환 (BFS, depth 제한)."""
    store = _get_store(path)
    try:
        related_pairs = store.get_related(node_id, relation=relation, depth=depth)
        return [
            WikiGraphEdge(source=node_id, target=target, relation=rel)
            for target, rel in related_pairs
        ]
    finally:
        store.close()


@router.get("/graph", response_model=WikiGraphData)
def wiki_graph(
    path: str = Query(...),
    node_id: str = Query(...),
    depth: int = Query(1, ge=1, le=3),
):
    """서브그래프 데이터 반환 (ReactFlow 형식). 최대 50 노드."""
    store = _get_store(path)
    try:
        conn = store._get_conn()

        # BFS로 관련 노드/엣지 수집
        visited: set[str] = {node_id}
        frontier = [node_id]
        graph_edges: list[WikiGraphEdge] = []
        node_ids: list[str] = [node_id]

        for _ in range(depth):
            if not frontier or len(node_ids) >= 50:
                break
            ph = ",".join("?" * len(frontier))
            rows = conn.execute(
                f"SELECT source, target, relation FROM wiki_edges WHERE source IN ({ph})",
                frontier,
            ).fetchall()
            new_frontier: list[str] = []
            for row in rows:
                src, tgt, rel = row["source"], row["target"], row["relation"]
                graph_edges.append(WikiGraphEdge(source=src, target=tgt, relation=rel))
                if tgt not in visited:
                    visited.add(tgt)
                    new_frontier.append(tgt)
                    node_ids.append(tgt)
                    if len(node_ids) >= 50:
                        break
            frontier = new_frontier

        # 노드 정보 조회
        graph_nodes: list[WikiGraphNode] = []
        for nid in node_ids:
            node = store.get(nid)
            if node:
                graph_nodes.append(WikiGraphNode(
                    id=node.id,
                    label=node.title,
                    type=node.type,
                    stale=node.stale,
                ))
            else:
                # stub: 미분석 노드
                parts = nid.split(":", 1)
                label = parts[1] if len(parts) == 2 else nid
                graph_nodes.append(WikiGraphNode(
                    id=nid, label=label, type="unknown", stale=False
                ))

        return WikiGraphData(nodes=graph_nodes, edges=graph_edges)
    finally:
        store.close()
