"""Graphing utilities for EventStreams"""
from __future__ import absolute_import, division, print_function

from functools import partial
import os
import re
from streamz.core import map
from streamz.sources import Source
from streamz.sinks import Sink
from collections import deque


def _clean_text(text, match=None):
    ''' Clean text, remove forbidden characters.
    '''
    # all non alpha numeric characters, except for _ and :
    # replace them with space
    # the + condenses a group of consecutive characters all into one space
    # (rather than assigning a space to each)
    if match is None:
        match = '[^a-zA-Z0-9_:]+'
    text = re.sub(match, ' ', text)
    # now replace the colon with semicolon
    text = re.sub(":", ";", text)
    return text


def build_node_set(node, s=None):
    """Build a set of all the nodes in a streamz graph

    Parameters
    ----------
    node : Stream
        The node to use as a starting point for building the set
    s : set or None
        The set to put the nodes into. If None return a new set full of nodes

    Returns
    -------
    s : set
        The set of nodes in the graph

    """
    if s is None:
        s = set()
    if node is None or (
        node in s
        and all(n in s for n in node.upstreams)
        and all(n in s for n in node.downstreams)
    ):
        return
    new_nodes = {n for n in node.downstreams}
    new_nodes.update(node.upstreams)
    new_nodes.add(node)
    s.update(new_nodes)
    [build_node_set(n, s) for n in list(new_nodes)]
    return s


def create_graph(node, graph, simplified=False):
    """Create networkx graph of the pipeline

    Parameters
    ----------
    node : Stream
        The node to start from
    graph : networkx.DiGraph
        The graph to fill with nodes
    simplified : bool, optional
        If True, only include Source, Sink and map nodes in the graph,
        connecting them directly. Defaults to False.

    Returns
    -------

    """
    # Step 1 build a set of all the nodes
    full_node_set = build_node_set(node)

    if not full_node_set:
        raise ValueError("No nodes found in the graph")

    if simplified:
        # Filter to keep only Source, Sink, and map nodes
        node_set = {n for n in full_node_set if isinstance(n, (map, Source, Sink))}

        # Add filtered nodes to the graph
        for n in node_set:
            t = hash(n)
            graph.add_node(
                t,
                label=_clean_text(str(n)),
                shape=getattr(n, '_graphviz_shape', 'ellipse'),
                orientation=str(getattr(n, '_graphviz_orientation', 0)),
                style=getattr(n, '_graphviz_style', 'rounded,filled'),
                fillcolor=getattr(n, '_graphviz_fillcolor', 'white'),
            )

        # Add edges, connecting nodes in the filtered set directly
        for start_node in node_set:
            start_hash = hash(start_node)
            visited_traversal = set()
            queue = deque(getattr(start_node, 'downstreams', []))

            while queue:
                current_node = queue.popleft()

                if current_node in visited_traversal:
                    continue
                visited_traversal.add(current_node)

                if current_node in node_set:
                    end_hash = hash(current_node)
                    if start_hash != end_hash:
                        if not graph.has_edge(start_hash, end_hash):
                            graph.add_edge(start_hash, end_hash)
                else:
                    # Continue searching downstream if it's not a target node type
                    # Check for downstreams attribute before extending
                    if hasattr(current_node, 'downstreams') and current_node.downstreams:
                        queue.extend(current_node.downstreams)

    else:
        # Original logic for adding all nodes
        node_set = full_node_set
        for n in node_set:
            t = hash(n)
            graph.add_node(
                t,
                label=_clean_text(str(n)),
                shape=n._graphviz_shape,
                orientation=str(n._graphviz_orientation),
                style=n._graphviz_style,
                fillcolor=n._graphviz_fillcolor,
            )

        # Original logic for adding all edges
        for n in node_set:
            t = hash(n)
            for nn in n.upstreams:
                # Only add edge if upstream is also in the (potentially filtered) node_set
                if nn in node_set:
                    tt = hash(nn)
                    graph.add_edge(tt, t)

            downstreams = n.downstreams
            for i, nn in enumerate(downstreams):
                # Only add edge if downstream is also in the (potentially filtered) node_set
                 if nn in node_set:
                    tt = hash(nn)
                    if len(downstreams) > 1:
                        graph.add_edge(t, tt, label=str(i))
                    else:
                        graph.add_edge(t, tt)

    # Step 4 destroy set
    del node_set
    del full_node_set


def readable_graph(graph):
    """Create human readable version of this object's task graph.

    Parameters
    ----------
    graph: nx.DiGraph instance
        The networkx graph representing the pipeline
    """
    import networkx as nx

    mapping = {k: "{}".format(graph.nodes[k]["label"]) for k in graph}
    idx_mapping = {}
    for k, v in mapping.items():
        if v in idx_mapping.keys():
            idx_mapping[v] += 1
            mapping[k] += "-{}".format(idx_mapping[v])
        else:
            idx_mapping[v] = 0

    gg = {k: v for k, v in mapping.items()}
    rg = nx.relabel_nodes(graph, gg, copy=True)
    return rg


def to_graphviz(graph, **graph_attr):
    import graphviz

    digraph_kwargs = {'name', 'comment', 'filename',
                      'format', 'engine', 'encoding',
                      'graph_attr', 'node_attr', 'edge_attr',
                      'body', 'strict', 'directory'}
    if not digraph_kwargs.intersection(graph_attr):
        graph_attr = dict(graph_attr=graph_attr)

    gvz = graphviz.Digraph(**graph_attr)
    for node, attrs in graph.nodes.items():
        gvz.node(node, **attrs)
    for edge, attrs in graph.edges().items():
        gvz.edge(edge[0], edge[1], **attrs)
    return gvz


def visualize(node, filename="mystream.png", simplified=False, **kwargs):
    """
    Render a task graph using dot.

    If `filename` is not None, write a file to disk with that name in the
    format specified by `format`.  `filename` should not include an extension.

    Parameters
    ----------
    node : Stream instance
        The stream to display.
    filename : str or None, optional
        The name (without an extension) of the file to write to disk.  If
        `filename` is None, no file will be written, and we communicate with
        dot using only pipes.  Default is 'mystream.png'.
    simplified : bool, optional
        If True, only display map, Source, and Sink nodes in the visualization,
        connecting them directly. Default False.
    format : {'png', 'pdf', 'dot', 'svg', 'jpeg', 'jpg'}, optional
        Format in which to write output file.  Default is 'png'.

    Returns
    -------
    result : None or IPython.display.Image or IPython.display.SVG  (See below.)

    Notes
    -----
    If IPython is installed, we return an IPython.display object in the
    requested format.  If IPython is not installed, we just return None.

    We always return None if format is 'pdf' or 'dot', because IPython can't
    display these formats natively. Passing these formats with filename=None
    will not produce any useful output.

    See Also
    --------
    streams.graph.readable_graph
    """
    import networkx as nx

    nx_g = nx.DiGraph()
    create_graph(node, nx_g, simplified=simplified)
    rg = readable_graph(nx_g)
    g = to_graphviz(rg, **kwargs)

    fmts = [".png", ".pdf", ".dot", ".svg", ".jpeg", ".jpg"]
    if filename is None:
        format = "png"

    elif any(filename.lower().endswith(fmt) for fmt in fmts):
        filename, format = os.path.splitext(filename)
        format = format[1:].lower()

    else:
        format = "png"

    try:
        data = g.pipe(format=format)
    except graphviz.backend.ExecutableNotFound as e:
         raise RuntimeError(
            "Graphviz executable not found. Make sure Graphviz is installed "
            "and available on your system\'s PATH. Error: {}".format(e)
        )

    if not data:
        raise RuntimeError(
            "Graphviz failed to properly produce an image. "
            "This probably means your installation of graphviz "
            "is missing png support. See: "
            "https://github.com/ContinuumIO/anaconda-issues/"
            "issues/485 for more information."
        )

    display_cls = _get_display_cls(format)

    if not filename:
        return display_cls(data=data)

    full_filename = ".".join([filename, format])
    try:
        with open(full_filename, "wb") as f:
            f.write(data)
    except Exception as e:
         raise RuntimeError(f"Failed to write graph to {full_filename}: {e}")

    return display_cls(filename=full_filename)


IPYTHON_IMAGE_FORMATS = frozenset(["jpeg", "png"])
IPYTHON_NO_DISPLAY_FORMATS = frozenset(["dot", "pdf"])


def _get_display_cls(format):
    """
    Get the appropriate IPython display class for `format`.

    Returns `IPython.display.SVG` if format=='svg', otherwise
    `IPython.display.Image`.

    If IPython is not importable, return dummy function that swallows its
    arguments and returns None.
    """
    dummy = lambda *args, **kwargs: None
    try:
        import IPython.display as display
    except ImportError:
        # Can't return a display object if no IPython.
        return dummy

    if format in IPYTHON_NO_DISPLAY_FORMATS:
        # IPython can't display this format natively, so just return None.
        return dummy
    elif format in IPYTHON_IMAGE_FORMATS:
        # Partially apply `format` so that `Image` and `SVG` supply a uniform
        # interface to the caller.
        return partial(display.Image, format=format)
    elif format == "svg":
        return display.SVG
    else:
        raise ValueError("Unknown format '%s' passed to `dot_graph`" % format)
