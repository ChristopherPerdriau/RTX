# This class will overlay the clinical information we have on hand
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
from QueryCOHD import QueryCOHD as COHD
# FIXME:^ this should be pulled from a YAML file pointing to the parser

# TODO: boy howdy this can be modularized quite a bit. Since COHD and other clinical KP's will be adding edge attributes and/or edges, should pull out functions to easy their addition.


class OverlayClinicalInfo:

    #### Constructor
    def __init__(self, response, message, params):
        self.response = response
        self.message = message
        self.parameters = params
        self.who_knows_about_what = {'COHD': ['chemical_substance', 'phenotypic_feature', 'disease']}  # FIXME: replace this with information about the KP's, KS's, and their API's
        self.node_curie_to_type = dict()
        self.global_iter = 0

    def decorate(self):
        """
        Main decorator: looks at parameters and figures out which subroutine to farm out to
        :param parameters:
        :return: response object
        """
        # First, make a dictionary between node curie and type to make sure we're only looking at edges we can handle
        self.response.info("Converting CURIE identifiers to human readable names")
        try:
            for node in self.message.knowledge_graph.nodes:
                self.node_curie_to_type[node.id] = node.type  # WARNING: this is a list
        except:
            tb = traceback.format_exc()
            error_type, error, _ = sys.exc_info()
            self.response.error(tb, error_code=error_type.__name__)
            self.response.error(f"Something went wrong when converting names")
            return self.response

        parameters = self.parameters
        if 'paired_concept_freq' in parameters:
            if parameters['paired_concept_freq'] == 'true':
                self.paired_concept_freq()
                # TODO: should I return the response and merge, or is it passed by reference and just return at the end?
        if 'associated_concept_freq' in parameters:
            if parameters['associated_concept_freq'] == 'true':
                #self.associated_concept_freq()  # TODO: make this function, and all the other COHD functions too
                pass
        if 'chi_square' in parameters:
            if parameters['chi_square'] == 'true':
                #self.chi_square()  # TODO: make this function, and all the other COHD functions too
                pass
        if 'observed_expected_ratio' in parameters:
            if parameters['observed_expected_ratio'] == 'true':
                self.observed_expected_ratio()  # TODO: make this function, and all the other COHD functions too
                pass
        if 'relative_frequency' in parameters:
            if parameters['relative_frequency'] == 'true':
                #self.associated_concept_freq()  # TODO: make this function, and all the other COHD functions too
                pass

        return self.response

    def in_common(self, list1, list2):
        """
        Helper function that returns true iff list1 and list2 have any elements in common
        :param list1: a list of strings (intended to be biolink node types)
        :param list2: another list of strings (intended to be biolink node types)
        :return: True/False if they share an element in common
        """
        if set(list1).intersection(set(list2)):
            return True
        else:
            return False

    def make_edge_attribute_from_curies(self, source_curie, target_curie, source_name="", target_name="", default=0, name=""):
        """
        Generic function to make an edge attribute
        :source_curie: CURIE of the source node for the edge under consideration
        :target_curie: CURIE of the target node for the edge under consideration
        :source_name: text name of the source node (in case the KP doesn't understand the CURIE)
        :target: text name of the target node (in case the KP doesn't understand the CURIE)
        :default: default value of the edge attribute
        :name: name of the KP functionality you want to apply
        """
        try:
            # edge attributes
            name = name
            type = "float"
            url = "http://cohd.smart-api.info/"
            value = default

            node_curie_to_type = self.node_curie_to_type
            source_type = node_curie_to_type[source_curie]
            target_type = node_curie_to_type[target_curie]
            # figure out which knowledge provider to use  # TODO: should handle this in a more structured fashion, does there exist a standardized KP API format?
            KP_to_use = None
            for KP in self.who_knows_about_what:
                # see which KP's can label both sources of information
                if self.in_common(source_type, self.who_knows_about_what[KP]) and self.in_common(target_type, self.who_knows_about_what[KP]):
                    KP_to_use = KP
            if KP_to_use == 'COHD':
                # convert CURIE to OMOP identifiers
                source_OMOPs = [str(x['omop_standard_concept_id']) for x in COHD.get_xref_to_OMOP(source_curie, 1)]
                target_OMOPs = [str(x['omop_standard_concept_id']) for x in COHD.get_xref_to_OMOP(target_curie, 1)]
                # FIXME: Super hacky way to get around the fact that COHD can't map CHEMBL drugs
                if source_curie.split('.')[0] == 'CHEMBL':
                    source_OMOPs = [str(x['concept_id']) for x in
                                    COHD.find_concept_ids(source_name, domain="Drug", dataset_id=3)]
                if target_curie.split('.')[0] == 'CHEMBL':
                    target_OMOPs = [str(x['concept_id']) for x in
                                    COHD.find_concept_ids(target_name, domain="Drug", dataset_id=3)]
                # uniquify everything
                source_OMOPs = list(set(source_OMOPs))
                target_OMOPs = list(set(target_OMOPs))
                # Decide how to handle the response from the KP
                if name == 'paired_concept_freq':
                    # sum up all frequencies  #TODO check with COHD people to see if this is kosher
                    frequency = default
                    for (omop1, omop2) in itertools.product(source_OMOPs, target_OMOPs):
                        freq_data = COHD.get_paired_concept_freq(omop1, omop2, 3)  # use the hierarchical dataset
                        if freq_data and 'concept_frequency' in freq_data:
                            frequency += freq_data['concept_frequency']
                    # decorate the edges
                    value = frequency
                elif name == 'observed_expected_ratio':
                    # TODO: looks like I could speed this up by taking advantage of the fact that if I don't specify concept_id_2, then it gets ALL concept ID's pretty quickly, would just need to then make a set/dict out of this and check if the others are in there
                    # should probably take the largest obs/exp ratio  # TODO: check with COHD people to see if this is kosher
                    # FIXME: the ln_ratio can be negative, so I should probably account for this, but the object model doesn't like -np.inf
                    value = float("-inf")  # FIXME: unclear in object model if attribute type dictates value type, or if value always needs to be a string
                    for (omop1, omop2) in itertools.product(source_OMOPs, target_OMOPs):
                        #print(f"{omop1},{omop2}")
                        response = COHD.get_obs_exp_ratio(omop1, concept_id_2=omop2, domain="", dataset_id=3)  # use the hierarchical dataset
                        # response is a list, since this function is overloaded and can omit concept_id_2, take the first element
                        if response and 'ln_ratio' in response[0]:
                            temp_val = response[0]['ln_ratio']
                            if temp_val > value:
                                value = temp_val
                # create the edge attribute
                edge_attribute = EdgeAttribute(type=type, name=name, value=str(value), url=url)  # populate the edge attribute # FIXME: unclear in object model if attribute type dictates value type, or if value always needs to be a string
                return edge_attribute
            else:
                return None
        except:
            tb = traceback.format_exc()
            error_type, error, _ = sys.exc_info()
            self.response.error(tb, error_code=error_type.__name__)
            self.response.error(f"Something went wrong when adding the edge attribute from {KP_to_use}.")

    def add_virtual_edge(self, name="", default=0):
        """
        Generic function to add a virtual edge to the KG an QG
        :name: name of the functionality of the KP to use
        """
        parameters = self.parameters
        source_curies_to_decorate = set()
        target_curies_to_decorate = set()
        curies_to_names = dict()  # FIXME: Super hacky way to get around the fact that COHD can't map CHEMBL drugs
        # identify the nodes that we should be adding virtual edges for
        for node in self.message.knowledge_graph.nodes:
            if hasattr(node, 'qnode_id'):
                if node.qnode_id == parameters['source_qnode_id']:
                    source_curies_to_decorate.add(node.id)
                    curies_to_names[
                        node.id] = node.name  # FIXME: Super hacky way to get around the fact that COHD can't map CHEMBL drugs
                if node.qnode_id == parameters['target_qnode_id']:
                    target_curies_to_decorate.add(node.id)
                    curies_to_names[
                        node.id] = node.name  # FIXME: Super hacky way to get around the fact that COHD can't map CHEMBL drugs
        added_flag = False  # check to see if any edges where added
        # iterate over all pairs of these nodes, add the virtual edge, decorate with the correct attribute
        for (source_curie, target_curie) in itertools.product(source_curies_to_decorate, target_curies_to_decorate):
            # create the edge attribute if it can be
            edge_attribute = self.make_edge_attribute_from_curies(source_curie, target_curie,
                                                                  source_name=curies_to_names[source_curie],
                                                                  target_name=curies_to_names[target_curie],
                                                                  default=default,
                                                                  name=name)
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

    def add_all_edges(self, name="", default=0):
        curies_to_names = dict()
        for node in self.message.knowledge_graph.nodes:
            curies_to_names[node.id] = node.name
        for edge in self.message.knowledge_graph.edges:
            if not edge.edge_attributes:  # populate if not already there
                edge.edge_attributes = []
            source_curie = edge.source_id
            target_curie = edge.target_id
            edge_attribute = self.make_edge_attribute_from_curies(source_curie, target_curie,
                                                                  source_name=curies_to_names[source_curie],
                                                                  target_name=curies_to_names[target_curie],
                                                                  default=default,
                                                                  name=name)  # FIXME: Super hacky way to get around the fact that COHD can't map CHEMBL drugs
            if edge_attribute:  # make sure an edge attribute was actually created
                edge.edge_attributes.append(edge_attribute)

    def paired_concept_freq(self, default=0):
        """
        calulate paired concept frequency.
        Retrieves observed clinical frequencies of a pair of concepts.
        :return: response
        """
        parameters = self.parameters
        self.response.debug("Computing paired concept frequencies.")
        self.response.info("Overlaying paired concept frequencies utilizing Columbia Open Health Data. This calls an external knowledge provider and may take a while")

        # Now add the edges or virtual edges
        try:
            if 'virtual_edge_type' in parameters:
                self.add_virtual_edge(name="paired_concept_freq", default=default)
            else:  # otherwise, just add to existing edges in the KG
                self.add_all_edges(name="paired_concept_freq", default=default)

        except:
            tb = traceback.format_exc()
            error_type, error, _ = sys.exc_info()
            self.response.error(tb, error_code=error_type.__name__)
            self.response.error(f"Something went wrong when overlaying clinical info")

    def observed_expected_ratio(self, default=0):
        """
        Returns the natural logarithm of the ratio between the observed count and expected count.
        Expected count is calculated from the single concept frequencies and assuming independence between the concepts.
        Results are returned as maximum over all ln_ratios matching to OMOP concept id.
        """
        parameters = self.parameters
        self.response.debug("Computing observed expected ratios.")
        self.response.info("Overlaying observed expected ratios utilizing Columbia Open Health Data. This calls an external knowledge provider and may take a while")

        # Now add the edges or virtual edges
        try:
            if 'virtual_edge_type' in parameters:
                self.add_virtual_edge(name="observed_expected_ratio", default=default)
            else:  # otherwise, just add to existing edges in the KG
                self.add_all_edges(name="observed_expected_ratio", default=default)

        except:
            tb = traceback.format_exc()
            error_type, error, _ = sys.exc_info()
            self.response.error(tb, error_code=error_type.__name__)
            self.response.error(f"Something went wrong when overlaying clinical info")
