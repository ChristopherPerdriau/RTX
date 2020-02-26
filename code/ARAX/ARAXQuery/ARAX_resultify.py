#!/usr/bin/env python3
import itertools
import os
import sys

__author__ = 'Stephen Ramsey'
__copyright__ = 'Oregon State University'
__credits__ = ['Stephen Ramsey', 'David Koslicki', 'Eric Deutsch']
__license__ = 'MIT'
__version__ = '0.1.0'
__maintainer__ = ''
__email__ = ''
__status__ = 'Prototype'


# is there a better way to import swagger_server?  Following SO posting 16981921
PACKAGE_PARENT = '../../UI/OpenAPI/python-flask-server'
SCRIPT_DIR = os.path.dirname(os.path.realpath(os.path.join(os.getcwd(), os.path.expanduser(__file__))))
sys.path.append(os.path.normpath(os.path.join(SCRIPT_DIR, PACKAGE_PARENT)))
from swagger_server.models.edge import Edge
from swagger_server.models.node import Node
from swagger_server.models.q_edge import QEdge
from swagger_server.models.q_node import QNode
from swagger_server.models.query_graph import QueryGraph
from swagger_server.models.knowledge_graph import KnowledgeGraph
from swagger_server.models.node_binding import NodeBinding
from swagger_server.models.edge_binding import EdgeBinding
from swagger_server.models.biolink_entity import BiolinkEntity
from swagger_server.models.result import Result
from swagger_server.models.message import Message
from typing import List, Dict, Set
from response import Response


# define a string-parameterized BiolinkEntity class
class BiolinkEntityStr(BiolinkEntity):
    def __init__(self, category_label: str):
        super().__init__()
        self.category_label = category_label

    def __str__(self):
        return super().__str__() + ":" + self.category_label


# define a map between category_label and BiolinkEntity object
BIOLINK_CATEGORY_LABELS = {'protein', 'disease', 'phenotypic_feature', 'gene', 'chemical_substance'}
BIOLINK_ENTITY_TYPE_OBJECTS = {category_label: BiolinkEntityStr(category_label) for
                               category_label in BIOLINK_CATEGORY_LABELS}


class ARAXResultify:
    def __init__(self):
        self.response = None
        self.message = None
        self.parameters = None
        self.allowable_actions = {
            'resultify'
        }

    def describe_me(self):
        """
        Little helper function for internal use that describes the actions and what they can do
        :return:
        """

        brief_description = """ `resultify` enumerates subgraphs of a knowledge graph (KG) that match a
pattern set by a query graph (QG) and sets the `results` data attribute of the
`message` object to be a list of `Result` objects, each corresponding to one of
the enumerated subgraphs. The matching between the KG subgraphs and the QG can
be forced to be sensitive to edge direction by setting
`ignore_edge_direction=false` (the default is to ignore edge direction). If any
query nodes in the QG have the `is_set` property set to `true`, this can be
overridden in `resultify` by including the query node `id` string (or the `id`
fields of more than one query node) in a parameter `force_isset_false` of type
`List[str]`.  """
        description_list = []
        params_dict = dict()
        params_dict['action'] = ['resultify']
        params_dict['brief_description'] = brief_description
        params_dict['force_isset_false'] = {'''a parameter of type `List(set)`
 containing string `id` fields of query nodes for which the `is_set` property
 should be set to `false`, overriding whatever the state of `is_set` for each
 of those nodes in the query graph. Optional.'''}
        params_dict['ignore_edge_direction'] = {'''a parameter of type `bool`
 indicating whether the direction of an edge in the knowledge graph should be
 taken into account when matching that edge to an edge in the query graph. By
 default, this parameter is `true`. Set this parameter to false in order to
 require that an edge in a subgraph of the KG will only match an edge in the QG
 if both have the same direction (taking into account the source/target node 
 mapping). Optional.'''}
        # TODO: will need to update manually if more self.parameters are added
        # eg. params_dict[node_id] = {"a query graph node ID or list of such id's (required)"} as per issue #640
        description_list.append(params_dict)
        return description_list

    def apply(self, input_message: Message, input_parameters: dict) -> Response:

        input_parameters['action'] = 'resultify'
        # Define a default response
        response = Response()
        self.response = response
        self.message = input_message

        # Basic checks on arguments
        if not isinstance(input_parameters, dict):
            response.error("Provided parameters is not a dict", error_code="ParametersNotDict")
            return response

        # list of actions that have so far been created for ARAX_overlay
        allowable_actions = self.allowable_actions

        # check to see if an action is actually provided
        if 'action' not in input_parameters:
            response.error(f"Must supply an action. Allowable actions are: action={allowable_actions}", error_code="MissingAction")
        elif input_parameters['action'] not in allowable_actions:
            response.error(f"Supplied action {input_parameters['action']} is not permitted. Allowable actions are: {allowable_actions}", error_code="UnknownAction")

        # Return if any of the parameters generated an error (showing not just the first one)
        if response.status != 'OK':
            return response

        # populate the parameters dict
        parameters = dict()
        for key, value in input_parameters.items():
            parameters[key] = value

        # Store these final parameters for convenience
        response.data['parameters'] = parameters
        self.parameters = parameters

        # convert the action string to a function call (so I don't need a ton of if statements
        getattr(self, '_' + self.__class__.__name__ + '__' + parameters['action'])()  # https://stackoverflow.com/questions/11649848/call-methods-by-string

        response.debug(f"Applying Resultifier to Message with parameters {parameters}")

        # Return the response and done
        return response

    def __resultify(self, describe: bool = False):
        """
        From a knowledge graph and a query graph (both in a Message object), extract a list of Results objects, each containing
        lists of NodeBinding and EdgeBinding objects. Add a list of Results objects to self.message.rseults.
        """
        assert self.response is not None
        results = self.message.results
        if results is not None and len(results) > 0:
            self.response.warning(f"Supplied response has nonzero number of entries. Must be empty")
            return

        message = self.message
        parameters = self.parameters
        kg = message.knowledge_graph
        qg = message.query_graph
        qg_nodes_override_treat_is_set_as_false_list = parameters.get('force_isset_false', None)
        if qg_nodes_override_treat_is_set_as_false_list is not None:
            qg_nodes_override_treat_is_set_as_false = set(qg_nodes_override_treat_is_set_as_false_list)
        else:
            qg_nodes_override_treat_is_set_as_false = set()
        ignore_edge_direction = parameters['ignore_edge_direction']
        try:
            results = get_results_for_kg_by_qg(kg,
                                               qg,
                                               qg_nodes_override_treat_is_set_as_false,
                                               ignore_edge_direction)
            message_code = 'OK'
            code_description = 'Result list computed from KG and QG'
        except Exception as e:
            code_description = str(e)
            message_code = e.__class__.__name__
            self.response.error(code_description)
            results = []
        message.results = results
        message.n_results = len(results)
        message.code_description = code_description
        message.message_code = message_code


def make_edge_key(node1_id: str,
                  node2_id: str) -> str:
    return node1_id + '->' + node2_id


def make_result_from_node_set(kg: KnowledgeGraph,
                              node_ids: Set[str]) -> Result:
    node_bindings = [NodeBinding(qg_id=node.qnode_id, kg_id=node.id) for node in kg.nodes if node.id in node_ids]
    edge_bindings = [EdgeBinding(qg_id=edge.qedge_id, kg_id=edge.id)
                     for edge in kg.edges if edge.source_id in node_ids and
                     edge.target_id in node_ids and
                     edge.qedge_id is not None]
    return Result(node_bindings=node_bindings,
                  edge_bindings=edge_bindings)


def get_results_for_kg_by_qg(kg: KnowledgeGraph,              # all nodes *must* have qnode_id specified
                             qg: QueryGraph,
                             qg_nodes_override_treat_is_set_as_false: set = None,
                             ignore_edge_direction: bool = True) -> List[Result]:

    kg_node_ids_without_qnode_id = [node.id for node in kg.nodes if node.qnode_id is None]
    if len(kg_node_ids_without_qnode_id) > 0:
        raise ValueError("these node IDs do not have qnode_id set: " + str(kg_node_ids_without_qnode_id))

    if qg_nodes_override_treat_is_set_as_false is None:
        qg_nodes_override_treat_is_set_as_false = set()

    # make a map of KG node IDs to QG node IDs, based on the node binding argument (nb) passed to this function
    node_bindings_map = {node.id: node.qnode_id for node in kg.nodes}

    # make a map of KG edge IDs to QG edge IDs, based on the node binding argument (nb) passed to this function
    edge_bindings_map = {edge.id: edge.qedge_id for edge in kg.edges if edge.qedge_id is not None}

    # make a map of KG node ID to KG edges, by source:
    kg_node_id_outgoing_adjacency_map: Dict[str, set] = {node.id: set() for node in kg.nodes}
    kg_node_id_incoming_adjacency_map: Dict[str, set] = {node.id: set() for node in kg.nodes}
    for edge in kg.edges:
        kg_node_id_outgoing_adjacency_map[edge.source_id].add(edge.target_id)
        kg_node_id_incoming_adjacency_map[edge.target_id].add(edge.source_id)

    # build up maps of node IDs to nodes, for both the KG and QG
    kg_nodes_map = {node.id: node for node in kg.nodes}
    qg_nodes_map = {node.id: node for node in qg.nodes}

    missing_node_ids = [node_id for node_id in qg_nodes_override_treat_is_set_as_false if node_id not in qg_nodes_map]
    if len(missing_node_ids) > 0:
        raise ValueError("the following nodes in qg_nodes_override_treat_is_set_as_false are not in the query graph: " +
                         str(missing_node_ids))

    # make an inverse "node bindings" map of QG node IDs to KG node ids
    reverse_node_bindings_map: Dict[str, set] = {node.id: set() for node in qg.nodes}
    for node in kg.nodes:
        reverse_node_bindings_map[node.qnode_id].add(node.id)

    # build up maps of edge IDs to edges, for both the KG and QG
    kg_edges_map = {edge.id: edge for edge in kg.edges}
    qg_edges_map = {edge.id: edge for edge in qg.edges}

    # make a map between QG edge keys and QG edge IDs
    qg_edge_key_to_edge_id_map = {make_edge_key(edge.source_id, edge.target_id): edge.id for edge in qg.edges}

    # --------------------- checking for validity of the NodeBindings list --------------
    # we require that every query graph node ID in the "values" slot of the node_bindings_map corresponds to an actual node in the QG
    node_ids_mapped_that_are_not_in_qg = [node_id for node_id in node_bindings_map.values() if node_id not in qg_nodes_map]
    if len(node_ids_mapped_that_are_not_in_qg) > 0:
        raise ValueError("query node ID specified in the NodeBinding list that is not in the QueryGraph: " + str(node_ids_mapped_that_are_not_in_qg))

    # we require that every know. graph node ID in the "keys" slot of the node_bindings_map corresponds to an actual node in the KG
    node_ids_mapped_that_are_not_in_kg = [node_id for node_id in node_bindings_map.keys() if node_id not in kg_nodes_map]
    if len(node_ids_mapped_that_are_not_in_kg) > 0:
        raise ValueError("knowledge graph node ID specified in the NodeBinding list that is not in the KG: " + str(node_ids_mapped_that_are_not_in_kg))

    # --------------------- checking for validity of the EdgeBindings list --------------
    # we require that every query graph edge ID in the "values" slot of the edge_bindings_map corresponds to an actual edge in the QG
    edge_ids_mapped_that_are_not_in_qg = [edge_id for edge_id in edge_bindings_map.values() if edge_id is not None and edge_id not in qg_edges_map]
    if len(edge_ids_mapped_that_are_not_in_qg) > 0:
        raise ValueError("query edge ID specified in the EdgeBinding list that is not in the QueryGraph: " + str(edge_ids_mapped_that_are_not_in_qg))

    # we require that every know. graph edge ID in the "keys" slot of the edge_bindings_map corresponds to an actual edge in the KG
    edge_ids_mapped_that_are_not_in_kg = [edge_id for edge_id in edge_bindings_map.keys() if edge_id not in kg_edges_map]
    if len(edge_ids_mapped_that_are_not_in_kg) > 0:
        raise ValueError("knowledge graph edge ID specified in the EdgeBinding list that is not in the KG: " + str(edge_ids_mapped_that_are_not_in_kg))

    # --------------------- checking that the node bindings cover the query graph --------------
    # check if each node in the query graph are hit by at least one node binding; if not, raise an exception
    qg_ids_hit_by_bindings = {node.qnode_id for node in kg.nodes}
    if len([node for node in qg.nodes if node.id not in qg_ids_hit_by_bindings]) > 0:
        raise ValueError("the node binding list does not cover all nodes in the query graph")

    # --------------------- checking that every KG node is bound to a QG node --------------
    node_ids_of_kg_that_are_not_mapped_to_qg = [node.id for node in kg.nodes if node.id not in node_bindings_map]
    if len(node_ids_of_kg_that_are_not_mapped_to_qg) > 0:
        raise ValueError("KG nodes that are not mapped to QG: " + str(node_ids_of_kg_that_are_not_mapped_to_qg))

    # --------------------- the source ID and target ID of every edge in KG should be a valid KG node ---------------------
    node_ids_for_edges_that_are_not_valid_nodes = [edge.source_id for edge in kg.edges if kg_nodes_map.get(edge.source_id, None) is None] +\
        [edge.target_id for edge in kg.edges if kg_nodes_map.get(edge.target_id, None) is None]
    if len(node_ids_for_edges_that_are_not_valid_nodes) > 0:
        raise ValueError("KG has edges that refer to the following non-existent nodes: " + str(node_ids_for_edges_that_are_not_valid_nodes))

    # --------------------- the source ID and target ID of every edge in QG should be a valid QG node ---------------------
    node_ids_for_edges_that_are_not_valid_nodes = [edge.source_id for edge in qg.edges if qg_nodes_map.get(edge.source_id, None) is None] +\
        [edge.target_id for edge in qg.edges if qg_nodes_map.get(edge.target_id, None) is None]
    if len(node_ids_for_edges_that_are_not_valid_nodes) > 0:
        raise ValueError("QG has edges that refer to the following non-existent nodes: " + str(node_ids_for_edges_that_are_not_valid_nodes))

    # --------------------- check for consistency of edge-to-node relationships, for all edge bindings -----------
    # check that for each bound KG edge, the QG mappings of the KG edges source and target nodes are also the
    # source and target nodes of the QG edge that corresponds to the bound KG edge
    for kg_edge_id in edge_bindings_map:
        kg_edge = kg_edges_map[kg_edge_id]
        kg_source_node_id = kg_edge.source_id
        kg_target_node_id = kg_edge.target_id
        qg_source_node_id = node_bindings_map[kg_source_node_id]
        qg_target_node_id = node_bindings_map[kg_target_node_id]
        if qg_edge_key_to_edge_id_map.get(make_edge_key(qg_source_node_id, qg_target_node_id), None) is None:
            if not ignore_edge_direction or qg_edge_key_to_edge_id_map.get(make_edge_key(qg_target_node_id, qg_source_node_id), None) is None:
                raise ValueError("The two nodes for KG edge " + kg_edge.id + ", " + kg_source_node_id + " and " +
                                 kg_target_node_id + ", have no corresponding edge in the QG")

    # ------- check that for every edge in the QG, any KG nodes that are bound to the QG endpoint nodes of the edge are connected in the KG -------
    for qg_edge in qg_edges_map.values():
        source_id_qg = qg_edge.source_id
        target_id_qg = qg_edge.target_id
        source_node_ids_kg = reverse_node_bindings_map[source_id_qg]
        target_node_ids_kg = reverse_node_bindings_map[target_id_qg]
        # for each source node ID, there should be an edge in KG from this source node to one of the nodes in target_node_ids_kg:
        for source_node_id_kg in source_node_ids_kg:
            if len(kg_node_id_outgoing_adjacency_map[source_node_id_kg] | target_node_ids_kg) == 0:
                raise ValueError("Inconsistent with its binding to the QG, the KG node: " + source_node_id_kg +
                                 " is not connected to *any* of the following nodes: " + str(target_node_ids_kg))
        for target_node_id_kg in target_node_ids_kg:
            if len(kg_node_id_incoming_adjacency_map[target_node_id_kg] | source_node_ids_kg) == 0:
                raise ValueError("Inconsistent with its binding to the QG, the KG node: " + target_node_id_kg +
                                 " is not connected to *any* of the following nodes: " + str(source_node_ids_kg))

    # ============= save until I can discuss with Eric whether there can be unmapped nodes in the KG =============
    # # if any node in the KG is not bound to a node in the QG, drop the KG node; redefine "kg" as the filtered KG
    # kg_node_ids_keep = {node.id for node in kg.nodes if node.id in node_bindings_map}
    # kg_nodes_keep_list = [node for node in kg.nodes if node.id in kg_node_ids_keep]
    # kg_edges_keep_list = [edge for edge in kg.edges if not (edge.source_id in kg_node_ids_keep and
    #                                                         edge.target_id in kg_node_ids_keep)]
    # kg = KnowledgeGraph(nodes=kg_nodes_keep_list,
    #                     edges=kg_edges_keep_list)
    # ============= save until I can discuss with Eric whether there can be unmapped nodes in the KG =============

    # Our goal is to enumerate all distinct "edge-maximal" subgraphs of the KG that each "covers"
    # the QG. A subgraph of KG that "covers" the QG is one for which all of the following conditions hold:
    # (1) under the KG-to-QG node bindings map, the range of the KG subgraph's nodes is the entire set of nodes in the QG
    # (2) for any QG node that has "is_set=True", *all* KG nodes that are bound to the same QG node are in the subgraph
    # (3) every edge in the QG is "covered" by at least one edge in the KG

    kg_node_ids_to_include_always: Set[str] = set()
    kg_node_id_lists_for_qg_nodes = []
    for node in qg.nodes:
        if node.is_set is not None and \
           node.is_set and \
           node.id not in qg_nodes_override_treat_is_set_as_false:
            kg_node_ids_to_include_always |= reverse_node_bindings_map[node.id]
        else:
            kg_node_id_lists_for_qg_nodes.append(list(reverse_node_bindings_map[node.id]))
    kg_node_ids_to_include_always_list = list(kg_node_ids_to_include_always)

    results: List[Result] = []
    for node_ids_for_subgraph_from_non_set_nodes in itertools.product(*kg_node_id_lists_for_qg_nodes):
        node_ids_for_subgraph = list(node_ids_for_subgraph_from_non_set_nodes) + kg_node_ids_to_include_always_list
        results.append(make_result_from_node_set(kg, set(node_ids_for_subgraph)))

    # Setting a description for each result is difficult, but is required by the database and should be there anyway.
    # Just put in a placeholder for now, as is done by the QueryGraphReasoner
    for result in results:
        result.description = "No description available"  # see issue 642

    return results


def test01():
    kg_node_info = ({'id': 'UniProtKB:12345',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'UniProtKB:23456',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'DOID:12345',
                     'type': 'disease',
                     'qnode_id': 'DOID:12345'},
                    {'id': 'HP:56789',
                     'type': 'phenotypic_feature',
                     'qnode_id': 'n02'},
                    {'id': 'HP:67890',
                     'type': 'phenotypic_feature',
                     'qnode_id': 'n02'},
                    {'id': 'HP:34567',
                     'type': 'phenotypic_feature',
                     'qnode_id': 'n02'})

    kg_edge_info = ({'edge_id': 'ke01',
                     'source_id': 'UniProtKB:12345',
                     'target_id': 'DOID:12345',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke02',
                     'source_id': 'UniProtKB:23456',
                     'target_id': 'DOID:12345',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke03',
                     'source_id': 'DOID:12345',
                     'target_id': 'HP:56789',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke04',
                     'source_id': 'DOID:12345',
                     'target_id': 'HP:67890',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke05',
                     'source_id': 'DOID:12345',
                     'target_id': 'HP:34567',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke06',
                     'source_id': 'HP:56789',
                     'target_id': 'HP:67890',
                     'qedge_id': None})

    kg_nodes = [Node(id=node_info['id'],
                     type=[node_info['type']],
                     qnode_id=node_info['qnode_id']) for node_info in kg_node_info]

    kg_edges = [Edge(id=edge_info['edge_id'],
                     source_id=edge_info['source_id'],
                     target_id=edge_info['target_id'],
                     qedge_id=edge_info['qedge_id']) for edge_info in kg_edge_info]

    knowledge_graph = KnowledgeGraph(kg_nodes, kg_edges)

    qg_node_info = ({'id': 'n01',
                     'type': 'protein',
                     'is_set': False},
                    {'id': 'DOID:12345',
                     'type': 'disease',
                     'is_set': False},
                    {'id': 'n02',
                     'type': 'phenotypic_feature',
                     'is_set': True})

    qg_edge_info = ({'edge_id': 'qe01',
                     'source_id': 'n01',
                     'target_id': 'DOID:12345'},
                    {'edge_id': 'qe02',
                     'source_id': 'DOID:12345',
                     'target_id': 'n02'})

    qg_nodes = [QNode(id=node_info['id'],
                      type=BIOLINK_ENTITY_TYPE_OBJECTS[node_info['type']],
                      is_set=node_info['is_set']) for node_info in qg_node_info]

    qg_edges = [QEdge(id=edge_info['edge_id'],
                      source_id=edge_info['source_id'],
                      target_id=edge_info['target_id']) for edge_info in qg_edge_info]

    query_graph = QueryGraph(qg_nodes, qg_edges)

    results_list = get_results_for_kg_by_qg(knowledge_graph,
                                            query_graph)

    assert len(results_list) == 2


def test02():
    kg_node_info = ({'id': 'UniProtKB:12345',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'UniProtKB:23456',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'DOID:12345',
                     'type': 'disease',
                     'qnode_id': 'DOID:12345'},
                    {'id': 'HP:56789',
                     'type': 'phenotypic_feature',
                     'qnode_id': 'n02'},
                    {'id': 'HP:67890',
                     'type': 'phenotypic_feature',
                     'qnode_id': 'n02'},
                    {'id': 'HP:34567',
                     'type': 'phenotypic_feature',
                     'qnode_id': 'n02'})

    kg_edge_info = ({'edge_id': 'ke01',
                     'source_id': 'UniProtKB:12345',
                     'target_id': 'DOID:12345',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke02',
                     'source_id': 'UniProtKB:23456',
                     'target_id': 'DOID:12345',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke03',
                     'source_id': 'DOID:12345',
                     'target_id': 'HP:56789',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke04',
                     'source_id': 'DOID:12345',
                     'target_id': 'HP:67890',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke05',
                     'source_id': 'DOID:12345',
                     'target_id': 'HP:34567',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke06',
                     'source_id': 'HP:56789',
                     'target_id': 'HP:67890',
                     'qedge_id': None})

    kg_nodes = [Node(id=node_info['id'],
                     type=[node_info['type']],
                     qnode_id=node_info['qnode_id']) for node_info in kg_node_info]

    kg_edges = [Edge(id=edge_info['edge_id'],
                     source_id=edge_info['source_id'],
                     target_id=edge_info['target_id'],
                     qedge_id=edge_info['qedge_id']) for edge_info in kg_edge_info]

    knowledge_graph = KnowledgeGraph(kg_nodes, kg_edges)

    qg_node_info = ({'id': 'n01',
                     'type': 'protein',
                     'is_set': None},
                    {'id': 'DOID:12345',
                     'type': 'disease',
                     'is_set': False},
                    {'id': 'n02',
                     'type': 'phenotypic_feature',
                     'is_set': True})

    qg_edge_info = ({'edge_id': 'qe01',
                     'source_id': 'n01',
                     'target_id': 'DOID:12345'},
                    {'edge_id': 'qe02',
                     'source_id': 'DOID:12345',
                     'target_id': 'n02'})

    qg_nodes = [QNode(id=node_info['id'],
                      type=BIOLINK_ENTITY_TYPE_OBJECTS[node_info['type']],
                      is_set=node_info['is_set']) for node_info in qg_node_info]

    qg_edges = [QEdge(id=edge_info['edge_id'],
                      source_id=edge_info['source_id'],
                      target_id=edge_info['target_id']) for edge_info in qg_edge_info]

    query_graph = QueryGraph(qg_nodes, qg_edges)

    results_list = get_results_for_kg_by_qg(knowledge_graph,
                                            query_graph)
    assert len(results_list) == 2


def test03():
    kg_node_info = ({'id': 'UniProtKB:12345',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'UniProtKB:23456',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'DOID:12345',
                     'type': 'disease',
                     'qnode_id': 'DOID:12345'},
                    {'id': 'HP:56789',
                     'type': 'phenotypic_feature',
                     'qnode_id': 'n02'},
                    {'id': 'HP:67890',
                     'type': 'phenotypic_feature',
                     'qnode_id': 'n02'},
                    {'id': 'HP:34567',
                     'type': 'phenotypic_feature',
                     'qnode_id': 'n02'})

    kg_edge_info = ({'edge_id': 'ke01',
                     'source_id': 'DOID:12345',
                     'target_id': 'UniProtKB:12345',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke02',
                     'source_id': 'UniProtKB:23456',
                     'target_id': 'DOID:12345',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke03',
                     'source_id': 'DOID:12345',
                     'target_id': 'HP:56789',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke04',
                     'source_id': 'DOID:12345',
                     'target_id': 'HP:67890',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke05',
                     'source_id': 'DOID:12345',
                     'target_id': 'HP:34567',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke06',
                     'source_id': 'HP:56789',
                     'target_id': 'HP:67890',
                     'qedge_id': None})

    kg_nodes = [Node(id=node_info['id'],
                     type=[node_info['type']],
                     qnode_id=node_info['qnode_id']) for node_info in kg_node_info]

    kg_edges = [Edge(id=edge_info['edge_id'],
                     source_id=edge_info['source_id'],
                     target_id=edge_info['target_id'],
                     qedge_id=edge_info['qedge_id']) for edge_info in kg_edge_info]

    knowledge_graph = KnowledgeGraph(kg_nodes, kg_edges)

    qg_node_info = ({'id': 'n01',
                     'type': 'protein',
                     'is_set': None},
                    {'id': 'DOID:12345',
                     'type': 'disease',
                     'is_set': False},
                    {'id': 'n02',
                     'type': 'phenotypic_feature',
                     'is_set': True})

    qg_edge_info = ({'edge_id': 'qe01',
                     'source_id': 'n01',
                     'target_id': 'DOID:12345'},
                    {'edge_id': 'qe02',
                     'source_id': 'DOID:12345',
                     'target_id': 'n02'})

    qg_nodes = [QNode(id=node_info['id'],
                      type=BIOLINK_ENTITY_TYPE_OBJECTS[node_info['type']],
                      is_set=node_info['is_set']) for node_info in qg_node_info]

    qg_edges = [QEdge(id=edge_info['edge_id'],
                      source_id=edge_info['source_id'],
                      target_id=edge_info['target_id']) for edge_info in qg_edge_info]

    query_graph = QueryGraph(qg_nodes, qg_edges)

    results_list = get_results_for_kg_by_qg(knowledge_graph,
                                            query_graph,
                                            ignore_edge_direction=True)
    assert len(results_list) == 2


def test04():
    kg_node_info = ({'id': 'UniProtKB:12345',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'UniProtKB:23456',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'DOID:12345',
                     'type': 'disease',
                     'qnode_id': 'DOID:12345'},
                    {'id': 'UniProtKB:56789',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'ChEMBL.COMPOUND:12345',
                     'type': 'chemical_substance',
                     'qnode_id': 'n02'},
                    {'id': 'ChEMBL.COMPOUND:23456',
                     'type': 'chemical_substance',
                     'qnode_id': 'n02'})

    kg_edge_info = ({'edge_id': 'ke01',
                     'source_id': 'ChEMBL.COMPOUND:12345',
                     'target_id': 'UniProtKB:12345',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke02',
                     'source_id': 'ChEMBL.COMPOUND:12345',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke03',
                     'source_id': 'ChEMBL.COMPOUND:23456',
                     'target_id': 'UniProtKB:12345',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke04',
                     'source_id': 'ChEMBL.COMPOUND:23456',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke05',
                     'source_id': 'DOID:12345',
                     'target_id': 'UniProtKB:12345',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke06',
                     'source_id': 'DOID:12345',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke08',
                     'source_id': 'UniProtKB:12345',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': None})

    kg_nodes = [Node(id=node_info['id'],
                     type=[node_info['type']],
                     qnode_id=node_info['qnode_id']) for node_info in kg_node_info]

    kg_edges = [Edge(id=edge_info['edge_id'],
                     source_id=edge_info['source_id'],
                     target_id=edge_info['target_id'],
                     qedge_id=edge_info['qedge_id']) for edge_info in kg_edge_info]

    knowledge_graph = KnowledgeGraph(kg_nodes, kg_edges)

    qg_node_info = ({'id': 'n01',
                     'type': 'protein',
                     'is_set': True},
                    {'id': 'DOID:12345',
                     'type': 'disease',
                     'is_set': False},
                    {'id': 'n02',
                     'type': 'chemical_substance',
                     'is_set': True})

    qg_edge_info = ({'edge_id': 'qe01',
                     'source_id': 'n02',
                     'target_id': 'n01'},
                    {'edge_id': 'qe02',
                     'source_id': 'DOID:12345',
                     'target_id': 'n01'})

    qg_nodes = [QNode(id=node_info['id'],
                      type=BIOLINK_ENTITY_TYPE_OBJECTS[node_info['type']],
                      is_set=node_info['is_set']) for node_info in qg_node_info]

    qg_edges = [QEdge(id=edge_info['edge_id'],
                      source_id=edge_info['source_id'],
                      target_id=edge_info['target_id']) for edge_info in qg_edge_info]

    query_graph = QueryGraph(qg_nodes, qg_edges)

    results_list = get_results_for_kg_by_qg(knowledge_graph,
                                            query_graph,
                                            qg_nodes_override_treat_is_set_as_false={'n02'},
                                            ignore_edge_direction=True)
    assert len(results_list) == 2


def test05():
    kg_node_info = ({'id': 'UniProtKB:12345',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'UniProtKB:23456',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'DOID:12345',
                     'type': 'disease',
                     'qnode_id': 'DOID:12345'},
                    {'id': 'UniProtKB:56789',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'ChEMBL.COMPOUND:12345',
                     'type': 'chemical_substance',
                     'qnode_id': 'n02'},
                    {'id': 'ChEMBL.COMPOUND:23456',
                     'type': 'chemical_substance',
                     'qnode_id': 'n02'})

    kg_edge_info = ({'edge_id': 'ke01',
                     'source_id': 'ChEMBL.COMPOUND:12345',
                     'target_id': 'UniProtKB:12345',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke02',
                     'source_id': 'ChEMBL.COMPOUND:12345',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke03',
                     'source_id': 'ChEMBL.COMPOUND:23456',
                     'target_id': 'UniProtKB:12345',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke04',
                     'source_id': 'ChEMBL.COMPOUND:23456',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': 'qe01'},    
                    {'edge_id': 'ke05',
                     'source_id': 'DOID:12345',
                     'target_id': 'UniProtKB:12345',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke06',
                     'source_id': 'DOID:12345',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke08',
                     'source_id': 'UniProtKB:12345',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': None})

    kg_nodes = [Node(id=node_info['id'],
                     type=[node_info['type']],
                     qnode_id=node_info['qnode_id']) for node_info in kg_node_info]

    kg_edges = [Edge(id=edge_info['edge_id'],
                     source_id=edge_info['source_id'],
                     target_id=edge_info['target_id'],
                     qedge_id=edge_info['qedge_id']) for edge_info in kg_edge_info]

    knowledge_graph = KnowledgeGraph(kg_nodes, kg_edges)

    qg_node_info = ({'id': 'n01',
                     'type': 'protein',
                     'is_set': True},
                    {'id': 'DOID:12345',
                     'type': 'disease',
                     'is_set': False},
                    {'id': 'n02',
                     'type': 'chemical_substance',
                     'is_set': True})

    qg_edge_info = ({'edge_id': 'qe01',
                     'source_id': 'n02',
                     'target_id': 'n01'},
                    {'edge_id': 'qe02',
                     'source_id': 'DOID:12345',
                     'target_id': 'n01'})

    qg_nodes = [QNode(id=node_info['id'],
                      type=BIOLINK_ENTITY_TYPE_OBJECTS[node_info['type']],
                      is_set=node_info['is_set']) for node_info in qg_node_info]

    qg_edges = [QEdge(id=edge_info['edge_id'],
                      source_id=edge_info['source_id'],
                      target_id=edge_info['target_id']) for edge_info in qg_edge_info]

    query_graph = QueryGraph(qg_nodes, qg_edges)

    message = Message(query_graph=query_graph,
                      knowledge_graph=knowledge_graph,
                      results=[])
    resultifier = ARAXResultify()
    input_parameters = {'ignore_edge_direction': True,
                        'force_isset_false': ['n02'],
                        'action': 'resultify'}
    resultifier.apply(message, input_parameters)
    assert resultifier.response.status == 'OK'
    assert len(resultifier.message.results) == 2


def test06():
    kg_node_info = ({'id': 'UniProtKB:12345',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'UniProtKB:23456',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'DOID:12345',
                     'type': 'disease',
                     'qnode_id': 'DOID:12345'},
                    {'id': 'UniProtKB:56789',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'ChEMBL.COMPOUND:12345',
                     'type': 'chemical_substance',
                     'qnode_id': 'n02'},
                    {'id': 'ChEMBL.COMPOUND:23456',
                     'type': 'chemical_substance',
                     'qnode_id': 'n02'})

    kg_edge_info = ({'edge_id': 'ke01',
                     'source_id': 'ChEMBL.COMPOUND:12345',
                     'target_id': 'UniProtKB:12345',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke02',
                     'source_id': 'ChEMBL.COMPOUND:12345',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke03',
                     'source_id': 'ChEMBL.COMPOUND:23456',
                     'target_id': 'UniProtKB:12345',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke04',
                     'source_id': 'ChEMBL.COMPOUND:23456',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': 'qe01'},    
                    {'edge_id': 'ke05',
                     'source_id': 'DOID:12345',
                     'target_id': 'UniProtKB:12345',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke06',
                     'source_id': 'DOID:12345',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke08',
                     'source_id': 'UniProtKB:12345',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': None})

    kg_nodes = [Node(id=node_info['id'],
                     type=[node_info['type']],
                     qnode_id=node_info['qnode_id']) for node_info in kg_node_info]

    kg_edges = [Edge(id=edge_info['edge_id'],
                     source_id=edge_info['source_id'],
                     target_id=edge_info['target_id'],
                     qedge_id=edge_info['qedge_id']) for edge_info in kg_edge_info]

    knowledge_graph = KnowledgeGraph(kg_nodes, kg_edges)

    qg_node_info = ({'id': 'n01',
                     'type': 'protein',
                     'is_set': True},
                    {'id': 'DOID:12345',
                     'type': 'disease',
                     'is_set': False},
                    {'id': 'n02',
                     'type': 'chemical_substance',
                     'is_set': True})

    qg_edge_info = ({'edge_id': 'qe01',
                     'source_id': 'n02',
                     'target_id': 'n01'},
                    {'edge_id': 'qe02',
                     'source_id': 'DOID:12345',
                     'target_id': 'n01'})

    qg_nodes = [QNode(id=node_info['id'],
                      type=BIOLINK_ENTITY_TYPE_OBJECTS[node_info['type']],
                      is_set=node_info['is_set']) for node_info in qg_node_info]

    qg_edges = [QEdge(id=edge_info['edge_id'],
                      source_id=edge_info['source_id'],
                      target_id=edge_info['target_id']) for edge_info in qg_edge_info]

    query_graph = QueryGraph(qg_nodes, qg_edges)

    message = Message(query_graph=query_graph,
                      knowledge_graph=knowledge_graph,
                      results=[])
    resultifier = ARAXResultify()
    input_parameters = {'ignore_edge_direction': True,
                        'force_isset_false': ['n07'],
                        'action': 'resultify'}
    resultifier.apply(message, input_parameters)
    assert resultifier.response.status != 'OK'
    assert len(resultifier.message.results) == 0


def test07():
    kg_node_info = ({'id': 'UniProtKB:12345',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'UniProtKB:23456',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'DOID:12345',
                     'type': 'disease',
                     'qnode_id': 'DOID:12345'},
                    {'id': 'UniProtKB:56789',
                     'type': 'protein',
                     'qnode_id': 'n01'},
                    {'id': 'ChEMBL.COMPOUND:12345',
                     'type': 'chemical_substance',
                     'qnode_id': 'n02'},
                    {'id': 'ChEMBL.COMPOUND:23456',
                     'type': 'chemical_substance',
                     'qnode_id': 'n02'})

    kg_edge_info = ({'edge_id': 'ke01',
                     'source_id': 'ChEMBL.COMPOUND:12345',
                     'target_id': 'UniProtKB:12345',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke02',
                     'source_id': 'ChEMBL.COMPOUND:12345',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke03',
                     'source_id': 'ChEMBL.COMPOUND:23456',
                     'target_id': 'UniProtKB:12345',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke04',
                     'source_id': 'ChEMBL.COMPOUND:23456',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': 'qe01'},
                    {'edge_id': 'ke05',
                     'source_id': 'DOID:12345',
                     'target_id': 'UniProtKB:12345',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke06',
                     'source_id': 'DOID:12345',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': 'qe02'},
                    {'edge_id': 'ke08',
                     'source_id': 'UniProtKB:12345',
                     'target_id': 'UniProtKB:23456',
                     'qedge_id': None})

    kg_nodes = [Node(id=node_info['id'],
                     type=[node_info['type']],
                     qnode_id=node_info['qnode_id']) for node_info in kg_node_info]

    kg_edges = [Edge(id=edge_info['edge_id'],
                     source_id=edge_info['source_id'],
                     target_id=edge_info['target_id'],
                     qedge_id=edge_info['qedge_id']) for edge_info in kg_edge_info]

    knowledge_graph = KnowledgeGraph(kg_nodes, kg_edges)

    qg_node_info = ({'id': 'n01',
                     'type': 'protein',
                     'is_set': True},
                    {'id': 'DOID:12345',
                     'type': 'disease',
                     'is_set': False},
                    {'id': 'n02',
                     'type': 'chemical_substance',
                     'is_set': True})

    qg_edge_info = ({'edge_id': 'qe01',
                     'source_id': 'n02',
                     'target_id': 'n01'},
                    {'edge_id': 'qe02',
                     'source_id': 'DOID:12345',
                     'target_id': 'n01'})

    qg_nodes = [QNode(id=node_info['id'],
                      type=BIOLINK_ENTITY_TYPE_OBJECTS[node_info['type']],
                      is_set=node_info['is_set']) for node_info in qg_node_info]

    qg_edges = [QEdge(id=edge_info['edge_id'],
                      source_id=edge_info['source_id'],
                      target_id=edge_info['target_id']) for edge_info in qg_edge_info]

    query_graph = QueryGraph(qg_nodes, qg_edges)

    response = Response()
    from actions_parser import ActionsParser
    actions_parser = ActionsParser()
    actions_list = ['resultify(ignore_edge_direction=true,force_isset_false=[n02])']
    result = actions_parser.parse(actions_list)
    response.merge(result)
    actions = result.data['actions']
    assert result.status == 'OK'
    resultifier = ARAXResultify()
    message = Message(query_graph=query_graph,
                      knowledge_graph=knowledge_graph,
                      results=[])
    result = resultifier.apply(message, actions[0]['parameters'])
    response.merge(result)
    assert len(message.results) == 2
    assert result.status == 'OK'


def test08():
    from ARAX_query import ARAXQuery
    araxq = ARAXQuery()
    query = {"previous_message_processing_plan": {"processing_actions": [
        "create_message",
        "add_qnode(type=disease, curie=DOID:731, id=n00)",
        "add_qnode(type=phenotypic_feature, is_set=false, id=n01)",
        "add_qedge(source_id=n00, target_id=n01, id=e00)",
        "query_graph_reasoner()",
        'resultify(ignore_edge_direction=true)',
        "return(message=true, store=false)"]}}
    response = Response()
    result = araxq.query(query)
    response.merge(result)
    assert result.status == 'OK'
    assert len(araxq.message.results) == 3223


def test09():
    from ARAX_query import ARAXQuery
    araxq = ARAXQuery()
    query = {"previous_message_processing_plan": {"processing_actions": [
            "create_message",
            "add_qnode(name=DOID:731, id=n00, type=disease, is_set=false)",
            "add_qnode(type=phenotypic_feature, is_set=false, id=n01)",
            "add_qedge(source_id=n00, target_id=n01, id=e00)",
            "expand(edge_id=e00)",
            'resultify(ignore_edge_direction=true)',
            "return(message=true, store=false)"]}}
    response = Response()
    result = araxq.query(query)
    response.merge(result)
    assert result.status == 'OK'
    assert len(araxq.message.results) == 3223

def test10():
    resultifier = ARAXResultify()
    desc = resultifier.describe_me()
    assert 'brief_description' in desc[0]
    assert 'force_isset_false' in desc[0]
    assert 'ignore_edge_direction' in desc[0]

def run_module_level_tests():
    test01()
    test02()
    test03()
    test04()


def run_arax_class_tests():
    test05()
    test06()
    test07()
    test08()
    test09()
    test10()

def main():
    run_module_level_tests()
    run_arax_class_tests()


if __name__ == '__main__':
    main()
