from .graph_spec import GraphSpec
from .roi import Roi
from .freezable import Freezable

import numpy as np
import networkx as nx

from copy import deepcopy
from typing import Dict, Optional, Set, Iterator, Any
import logging
import itertools


logger = logging.getLogger(__name__)


class Vertex(Freezable):
    """
    A stucture representing each vertex in a Graph.

    Args:

        id (``int``):

            A unique identifier for this Vertex

        location (``np.ndarray``):

            A numpy array containing a nodes location

        Optional attrs (``dict``, str -> ``Any``):

            A dictionary containing a mapping from attribute to value.
            Used to store any extra attributes associated with the
            Vertex such as color, size, etc.

        Optional temporary (bool):

            A tag to mark a node as temporary. Some operations such
            as `trim` might make new nodes that are just biproducts
            of viewing the data with a limited scope. These nodes
            are only guaranteed to have an id different from those
            in the same Graph, but may have conflicts if you request
            multiple graphs from the same source with different rois.
    """

    def __init__(
        self,
        id: int,
        location: np.ndarray,
        temporary: bool = False,
        attrs: Optional[Dict[str, Any]] = None,
    ):
        self.__id = id
        self.__location = location
        self.__temporary = temporary
        self.attrs = attrs
        self.freeze()

    @property
    def location(self):
        assert isinstance(self.__location, np.ndarray)
        return self.__location

    @location.setter
    def location(self, new_location):
        self.__location = new_location

    @property
    def attrs(self):
        return self.__attrs

    @attrs.setter
    def attrs(self, attrs):
        self.__attrs = attrs if attrs is not None else {}

    @property
    def id(self):
        return self.__id

    @property
    def original_id(self):
        return self.id if not self.temporary else None

    @property
    def temporary(self):
        return self.__temporary

    @property
    def all(self):
        data = self.__attrs
        data["id"] = self.id
        data["location"] = self.location
        data["temporary"] = self.temporary
        return data

    @classmethod
    def from_attrs(cls, attrs: Dict[str, Any]):
        special_attrs = ["id", "location", "temporary"]
        vertex_id = attrs["id"]
        location = attrs["location"]
        temporary = attrs["temporary"]
        remaining_attrs = {k: v for k, v in attrs.items() if k not in special_attrs}
        return cls(
            id=vertex_id, location=location, temporary=temporary, attrs=remaining_attrs
        )

    def __str__(self):
        return f"Vertex({self.temporary}) ({self.id}) at ({self.location})"

    def __repr__(self):
        return str(self)


class Edge(Freezable):
    """
    A structure representing edges in a graph.

    Args:

        u (``int``)

            The id of the 'u' node of this edge

        v (``int``)

            the id of the `v` node of this edge
    """

    def __init__(self, u: int, v: int, attrs: Optional[Dict[str, Any]] = None):
        self.__u = u
        self.__v = v
        self.__attrs = attrs if attrs is not None else {}
        self.freeze()

    @property
    def u(self):
        return self.__u

    @property
    def v(self):
        return self.__v

    @property
    def all(self):
        return self.__attrs

    def __iter__(self):
        return iter([self.u, self.v])

    def __str__(self):
        return f"({self.u}, {self.v})"

    def __repr__(self):
        return f"({self.u}, {self.v})"

    def __eq__(self, other):
        return self.u == other.u and self.v == other.v

    def __hash__(self):
        return hash((self.u, self.v))

    def directed_eq(self, other):
        return self.u == other.u and self.v == other.v

    def undirected_eq(self, other):
        return set([self.u, self.v]) == set([other.u, other.v])


class Graph(Freezable):
    """A structure containing a list of :class:`Vertex`, a list of :class:'Edge',
    and a specification describing the data.

    Args:

        vertices (``iterator``, :class:`Vertex`):

            An iterator containing Vertices.

        edges (``iterator``, :class:`Edge`):

            An iterator containing Edges.

        spec (:class:`GraphSpec`):

            A spec describing the data.
    """

    def __init__(
        self, vertices: Iterator[Vertex], edges: Iterator[Edge], spec: GraphSpec
    ):
        self.__spec = spec
        self.__graph = self.create_graph(vertices, edges)

    @property
    def spec(self):
        return self.__spec

    @spec.setter
    def spec(self, new_spec):
        self.__spec = new_spec

    @property
    def directed(self):
        return self.spec.directed

    def create_graph(self, vertices: Iterator[Vertex], edges: Iterator[Edge]):
        if self.directed:
            graph = nx.DiGraph()
        else:
            graph = nx.Graph()

        for vertex in vertices:
            vertex.location = vertex.location.astype(self.spec.dtype)

        vs = [(v.id, v.all) for v in vertices]
        graph.add_nodes_from(vs)
        graph.add_edges_from([(e.u, e.v, e.all) for e in edges])
        return graph

    @property
    def vertices(self):
        for vertex_id, vertex_attrs in self.__graph.nodes.items():
            v = Vertex.from_attrs(vertex_attrs)
            if not np.issubdtype(v.location.dtype, self.spec.dtype):
                raise Exception()
            yield v

    def num_vertices(self):
        return self.__graph.number_of_nodes()

    @property
    def edges(self):
        for (u, v), attrs in self.__graph.edges.items():
            yield Edge(u, v, attrs)

    def neighbors(self, vertex):
        for neighbor in self.__graph.successors(vertex.id):
            yield Vertex.from_attrs(self.__graph.nodes[neighbor])
        if self.directed:
            for neighbor in self.__graph.predecessors(vertex.id):
                yield Vertex.from_attrs(self.__graph.nodes[neighbor])

    def __str__(self):
        string = "Vertices:\n"
        for vertex in self.vertices:
            string += f"{vertex}\n"
        string += "Edges:\n"
        for edge in self.edges:
            string += f"{edge}\n"
        return string

    def __repr__(self):
        return str(self)

    def vertex(self, id: int):
        """
        Get vertex with a specific id
        """
        attrs = self.__graph.nodes[id]
        return Vertex.from_attrs(attrs)

    def remove_vertex(self, vertex: Vertex):
        """
        Remove a vertex
        """
        self.__graph.remove_node(vertex.id)

    def add_vertex(self, vertex: Vertex):
        """
        Adds a vertex to the graph.
        If a vertex exists with the same id as the vertex you are adding,
        its attributes will be overwritten.
        """
        vertex.location = vertex.location.astype(self.spec.dtype)
        self.__graph.add_node(vertex.id, **vertex.all)

    def remove_edge(self, edge: Edge):
        """
        Remove an edge from the graph.
        """
        self.__graph.remove_edge(edge.u, edge.v)

    def add_edge(self, edge: Edge):
        """
        Adds an edge to the graph.
        If an edge exists with the same u and v, its attributes
        will be overwritten.
        """
        self.__graph.add_edge(edge.u, edge.v, **edge.all)

    def copy(self):
        return deepcopy(self)

    def crop(self, roi: Roi, copy: bool = True):
        """
        Will remove all vertices from self that are not contained in `roi` except for
        "dangling" vertices. This means that if there are vertices A, B s.t. there
        is an edge (A, B) and A is contained in `roi` but B is not, the edge (A, B)
        is considered contained in the `roi` and thus vertex B will be kept as a
        "dangling" vertex.

        Note there is a helper function `trim` that will remove B and replace it with
        a node at the intersection of the edge (A, B) and the bounding box of `roi`.
        """

        if not copy:
            raise NotImplementedError("subgraph view not yet supported")

        if copy:
            cropped = self.copy()
        else:
            cropped = self
        cropped.__spec = self.__spec

        contained_nodes = set(
            [v.id for v in cropped.vertices if roi.contains(v.location)]
        )
        all_contained_edges = set(
            [
                e
                for e in cropped.edges
                if e.u in contained_nodes or e.v in contained_nodes
            ]
        )
        fully_contained_edges = set(
            [
                e
                for e in all_contained_edges
                if e.u in contained_nodes and e.v in contained_nodes
            ]
        )
        partially_contained_edges = all_contained_edges - fully_contained_edges
        contained_edge_nodes = set(list(itertools.chain(*all_contained_edges)))
        all_nodes = contained_edge_nodes | contained_nodes
        dangling_nodes = all_nodes - contained_nodes

        for vertex in list(cropped.vertices):
            if vertex.id not in all_nodes:
                cropped.remove_vertex(vertex)
        for edge in list(cropped.edges):
            if edge not in all_contained_edges:
                cropped.remove_edge(edge)

        cropped.spec.roi = roi
        return cropped

    def shift(self, offset):
        for vertex in self.vertices:
            vertex.location += offset

    def new_graph(self):
        if self.directed():
            return nx.DiGraph()
        else:
            return nx.Graph()

    def trim(self, roi: Roi):
        """
        Create a copy of self and replace "dangling" vertices with contained vertices.

        A "dangling" vertex is defined by: Let A, B be vertices s.t. there exists an
        edge (A, B) and A is contained in `roi` but B is not. Edge (A, B) is considered
        contained, and thus B is kept as a "dangling" vertex.
        """

        trimmed = self.copy()

        contained_nodes = set(
            [v.id for v in trimmed.vertices if roi.contains(v.location)]
        )
        all_contained_edges = set(
            [
                e
                for e in trimmed.edges
                if e.u in contained_nodes or e.v in contained_nodes
            ]
        )
        fully_contained_edges = set(
            [
                e
                for e in all_contained_edges
                if e.u in contained_nodes and e.v in contained_nodes
            ]
        )
        partially_contained_edges = all_contained_edges - fully_contained_edges
        contained_edge_nodes = set(list(itertools.chain(*all_contained_edges)))
        all_nodes = contained_edge_nodes | contained_nodes
        dangling_nodes = all_nodes - contained_nodes

        trimmed._handle_boundaries(
            partially_contained_edges,
            contained_nodes,
            roi,
            node_id=itertools.count(max(all_nodes) + 1),
        )

        for vertex in trimmed.vertices:
            assert roi.contains(
                vertex.location
            ), f"Failed to properly contain vertex {vertex.id} at {vertex.location}"

        return trimmed

    def _handle_boundaries(
        self,
        crossing_edges: Iterator[Edge],
        contained_nodes: Set[int],
        roi: Roi,
        node_id: Iterator[int],
    ):
        for e in crossing_edges:
            u, v = self.vertex(e.u), self.vertex(e.v)
            u_in = u.id in contained_nodes
            v_in, v_out = (u, v) if u_in else (v, u)
            in_location, out_location = (v_in.location, v_out.location)
            new_location = self._roi_intercept(in_location, out_location, roi)
            if not all(np.isclose(new_location, in_location)):
                # use deepcopy because modifying this vertex should not modify original
                new_attrs = deepcopy(v_out.attrs)
                new_v = Vertex(
                    id=next(node_id),
                    location=new_location,
                    attrs=new_attrs,
                    temporary=True,
                )
                new_e = Edge(
                    u=v_in.id if u_in else new_v.id, v=new_v.id if u_in else v_in.id
                )
                self.add_vertex(new_v)
                self.add_edge(new_e)
            self.remove_edge(e)
            self.remove_vertex(v_out)

    def _roi_intercept(
        self, inside: np.ndarray, outside: np.ndarray, bb: Roi
    ) -> np.ndarray:
        """
        Given two points, one inside a bounding box and one outside,
        get the intercept between the line and the bounding box.
        """

        offset = outside - inside
        distance = np.linalg.norm(offset)
        assert not np.isclose(distance, 0), f"Inside and Outside are the same location"
        direction = offset / distance

        # `offset` can be 0 on some but not all axes leaving a 0 in the denominator.
        # `inside` can be on the bounding box, leaving a 0 in the numerator.
        # `x/0` throws a division warning, `0/0` throws an invalid warning (both are fine here)
        with np.errstate(divide="ignore", invalid="ignore"):
            bb_x = np.asarray(
                [
                    (np.asarray(bb.get_begin()) - inside) / offset,
                    (np.asarray(bb.get_end()) - inside) / offset,
                ],
                dtype=self.spec.dtype,
            )

        with np.errstate(invalid="ignore"):
            s = np.min(bb_x[np.logical_and((bb_x >= 0), (bb_x <= 1))])

        new_location = inside + s * distance * direction
        upper = np.array(bb.get_end(), dtype=self.spec.dtype)
        new_location = np.clip(
            new_location, bb.get_begin(), upper - upper * np.finfo(self.spec.dtype).eps
        )
        return new_location

    def merge(self, other, copy_from_self=False, copy=False):
        """
        Merge this graph with another. The resulting graph will have the Roi
        of the larger one.

        This only works if one of the two graphs contains the other.
        In this case, ``other`` will overwrite edges and vertices with the same
        ID in ``self`` (unless ``copy_from_self`` is set to ``True``).
        Vertices and edges in ``self`` that are contained in the Roi of ``other``
        will be removed (vice versa for ``copy_from_self``)

        A copy will only be made if necessary or ``copy`` is set to ``True``.
        """

        # It is unclear how to merge points in all cases. Consider a 10x10 graph,
        # you crop out a 5x5 area, do a shift augment, and attempt to merge.
        # What does that mean? specs have changed. It should be a new key.
        raise NotImplementedError("Merge function should not be used!")

        self_roi = self.spec.roi
        other_roi = other.spec.roi

        assert self_roi.contains(other_roi) or other_roi.contains(
            self_roi
        ), "Can not merge graphs that are not contained in each other."

        # make sure self contains other
        if not self_roi.contains(other_roi):
            return other.merge(self, not copy_from_self, copy)

        # edges and vertices in addition are guaranteed to be in merged
        base = other if copy_from_self else self
        addition = self if copy_from_self else other

        if copy:
            merged = deepcopy(base)
        else:
            merged = base

        for vertex in list(merged.vertices):
            if merged.spec.roi.contains(vertex.location):
                merged.remove_vertex(vertex)
        for edge in list(merged.edges):
            if merged.spec.roi.contains(
                merged.vertex(edge.u)
            ) or merged.spec.roi.contains(merged.vertex(edge.v)):
                merged.remove_edge(edge)
        for vertex in addition.vertices:
            merged.add_vertex(vertex)
        for edge in addition.edges:
            merged.add_edge(edge)

        return merged


class GraphKey(Freezable):
    """A key to identify graphs in requests, batches, and across
    nodes.

    Used as key in :class:`BatchRequest` and :class:`Batch` to retrieve specs
    or graphs.

    Args:

        identifier (``string``):

            A unique, human readable identifier for this graph key. Will be
            used in log messages and to look up graphs in requests and batches.
            Should be upper case (like ``CENTER_GRAPH``). The identifier is
            unique: Two graph keys with the same identifier will refer to the
            same graph.
    """

    def __init__(self, identifier):
        self.identifier = identifier
        self.hash = hash(identifier)
        self.freeze()
        logger.debug("Registering graph type %s", self)
        setattr(GraphKeys, self.identifier, self)

    def __eq__(self, other):
        return hasattr(other, "identifier") and self.identifier == other.identifier

    def __hash__(self):
        return self.hash

    def __repr__(self):
        return self.identifier


class GraphKeys:
    """Convenience access to all created :class:`GraphKey`s. A key generated
    with::

        centers = GraphKey('CENTER_GRAPH')

    can be retrieved as::

        GraphKeys.CENTER_GRAPH
    """

    pass
