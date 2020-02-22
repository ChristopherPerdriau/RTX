# This class will overlay the normalized google distance on a message (all edges)
#!/bin/env python3
import sys
import os
import traceback
import numpy as np
import itertools
from datetime import datetime

# relative imports
sys.path.append(os.path.dirname(os.path.abspath(__file__))+"/../OpenAPI/python-flask-server/")
from swagger_server.models.edge_attribute import EdgeAttribute
from swagger_server.models.edge import Edge
from swagger_server.models.q_edge import QEdge
sys.path.append(os.path.dirname(os.path.abspath(__file__))+"/../../reasoningtool/kg-construction/")
from NormGoogleDistance import NormGoogleDistance as NGD


class ComputeNGD:

    #### Constructor
    def __init__(self, response, message, parameters):
        self.response = response
        self.message = message
        self.parameters = parameters
        self.global_iter = 0

    def compute_ngd(self):
        """
        Iterate over all the edges in the knowledge graph, compute the normalized google distance and stick that info
        on the edge_attributes
        :default: The default value to set for NGD if it returns a nan
        :return: response
        """
        parameters = self.parameters
        self.response.debug(f"Computing NGD")
        self.response.info(f"Computing the normalized Google distance: weighting edges based on source/target node "
                           f"co-occurrence frequency in PubMed abstracts")

        self.response.info("Converting CURIE identifiers to human readable names")
        node_curie_to_name = dict()
        try:
            for node in self.message.knowledge_graph.nodes:
                node_curie_to_name[node.id] = node.name
        except:
            tb = traceback.format_exc()
            error_type, error, _ = sys.exc_info()
            self.response.error(f"Something went wrong when converting names")
            self.response.error(tb, error_code=error_type.__name__)


        self.response.warning(f"Utilizing API calls to NCBI eUtils, so this may take a while...")
        name = "ngd"
        type = "float"
        value = self.parameters['default_value']
        url = "https://arax.rtx.ai/api/rtx/v1/ui/#/PubmedMeshNgd"

        # if you want to add virtual edges, identify the source/targets, decorate the edges, add them to the KG, and then add one to the QG corresponding to them
        if 'virtual_edge_type' in parameters:
            source_curies_to_decorate = set()
            target_curies_to_decorate = set()
            curies_to_names = dict()
            # identify the nodes that we should be adding virtual edges for
            for node in self.message.knowledge_graph.nodes:
                if hasattr(node, 'qnode_id'):
                    if node.qnode_id == parameters['source_qnode_id']:
                        source_curies_to_decorate.add(node.id)
                        curies_to_names[
                            node.id] = node.name
                    if node.qnode_id == parameters['target_qnode_id']:
                        target_curies_to_decorate.add(node.id)
                        curies_to_names[
                            node.id] = node.name
            added_flag = False  # check to see if any edges where added
            # iterate over all pairs of these nodes, add the virtual edge, decorate with the correct attribute
            for (source_curie, target_curie) in itertools.product(source_curies_to_decorate, target_curies_to_decorate):
                # create the edge attribute if it can be
                source_name = curies_to_names[source_curie]
                target_name = curies_to_names[target_curie]
                ngd_value = NGD.get_ngd_for_all([source_curie, target_curie], [source_name, target_name])
                if np.isfinite(ngd_value):  # if ngd is finite, that's ok, otherwise, stay with default
                    value = ngd_value
                edge_attribute = EdgeAttribute(type=type, name=name, value=str(value), url=url)  # populate the NGD edge attribute
                if edge_attribute:
                    added_flag = True
                    # make the edge, add the attribute

                    # edge properties
                    now = datetime.now()
                    edge_type = parameters['virtual_edge_type']
                    relation = name
                    is_defined_by = "https://arax.rtx.ai/api/rtx/v1/ui/"
                    defined_datetime = now.strftime("%Y-%m-%d %H:%M:%S")
                    provided_by = "ARAX/RTX"
                    confidence = 1.0
                    weight = None  # TODO: could make the actual value of the attribute
                    source_id = source_curie
                    target_id = target_curie

                    # now actually add the virtual edges in
                    id = f"{edge_type}_{self.global_iter}"
                    self.global_iter += 1
                    edge = Edge(id=id, type=edge_type, relation=relation, source_id=source_id,
                                target_id=target_id,
                                is_defined_by=is_defined_by, defined_datetime=defined_datetime,
                                provided_by=provided_by,
                                confidence=confidence, weight=weight, edge_attributes=[edge_attribute])
                    self.message.knowledge_graph.edges.append(edge)

            # Now add a q_edge the query_graph since I've added an extra edge to the KG
            if added_flag:
                edge_type = parameters['virtual_edge_type']
                relation = name
                q_edge = QEdge(id=edge_type, type=edge_type, relation=relation,
                               source_id=parameters['source_qnode_id'], target_id=parameters[
                        'target_qnode_id'])  # TODO: ok to make the id and type the same thing?
                self.message.query_graph.edges.append(q_edge)
        else:  # you want to add it for each edge in the KG
            # iterate over KG edges, add the information
            try:
                for edge in self.message.knowledge_graph.edges:
                    # Make sure the edge_attributes are not None
                    if not edge.edge_attributes:
                        edge.edge_attributes = []  # should be an array, but why not a list?
                    # now go and actually get the NGD
                    source_curie = edge.source_id
                    target_curie = edge.target_id
                    source_name = node_curie_to_name[source_curie]
                    target_name = node_curie_to_name[target_curie]
                    ngd_value = NGD.get_ngd_for_all([source_curie, target_curie], [source_name, target_name])
                    if np.isfinite(ngd_value):  # if ngd is finite, that's ok, otherwise, stay with default
                        value = ngd_value
                    ngd_edge_attribute = EdgeAttribute(type=type, name=name, value=str(value), url=url)  # populate the NGD edge attribute
                    edge.edge_attributes.append(ngd_edge_attribute)  # append it to the list of attributes
            except:
                tb = traceback.format_exc()
                error_type, error, _ = sys.exc_info()
                self.response.error(tb, error_code=error_type.__name__)
                self.response.error(f"Something went wrong adding the NGD edge attributes")
            else:
                self.response.info(f"NGD values successfully added to edges")

            return self.response