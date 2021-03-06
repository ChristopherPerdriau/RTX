from SynonymMapper import SynonymMapper
from QueryMyChem import QueryMyChem

import os
import sys
import time
import networkx
import obonet
# import requests_cache

try:
    from QueryUMLSApi import QueryUMLSApi
except ImportError:
    insert_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)) + "/../SemMedDB/")
    sys.path.insert(0, insert_dir)
    from QueryUMLSApi import QueryUMLS


class DrugMapper:
    graph = obonet.read_obo("https://raw.githubusercontent.com/obophenotype/human-phenotype-ontology/master/hp.obo")

    @staticmethod
    def __map_umls_to_onto_id(umls_array):
        """
        mapping between umls ids and ontology ids including omim, doid, and hp.
        :param umls_array:
        :return: a set of strings containing the found hp / omim / doid ids or empty set if none were found
        """
        onto_set = set()
        sm = SynonymMapper()
        for umls_id in umls_array:
            onto_ids = sm.get_all_from_oxo(umls_id, ['DOID', 'OMIM', 'HP'])
            if onto_ids is not None:
                for onto_id in onto_ids:
                    onto_set.add(onto_id)
        return onto_set

    @staticmethod
    def map_drug_to_hp_with_side_effects(chembl_id):
        """
        mapping between a drug and human phenotypes corresponding to side effects

        :param chembl_id: The CHEMBL ID for a drug

        :return: A set of strings containing the found hp ids or empty set if none where found
        """
        hp_set = set()
#        global graph
        if not isinstance(chembl_id, str):
            return hp_set
        umls_set = QueryMyChem.get_drug_side_effects(chembl_id)
        meddra_set = QueryMyChem.get_meddra_codes_for_side_effects(chembl_id)
        if len(umls_set) == 0 and len(meddra_set) == 0:
            return hp_set
        sm = SynonymMapper()

        for meddra_code in meddra_set:
            hp_ids = DrugMapper.map_meddra_to_hp(meddra_code, DrugMapper.graph)
            if len(hp_ids) > 0:
                for hp_id in hp_ids:
                    hp_set.add(hp_id)

        for umls_id in umls_set:
            hp_ids = sm.get_all_from_oxo(umls_id, 'HP')
            if hp_ids is not None:
                for hp_id in hp_ids:
                    hp_set.add(hp_id)

        return hp_set

    @staticmethod
    def make_meddra_to_hp_map(graph):
        res_dict = {}
        for node_name in graph:
            # get the node's properties
            node_properties_dict = graph.node[node_name]
            xref_list = node_properties_dict.get('xref', None)
            if xref_list is not None:
                for xref_curie in xref_list:
                    if xref_curie.startswith('MEDDRA:'):
                        res_dict[xref_curie[:15]] = node_name
        return res_dict

    meddra_to_hp_map = make_meddra_to_hp_map.__func__(graph)

    @staticmethod
    def map_meddra_to_hp(medra_curie, graph):
        ret_hp_set = set()
#        meddra_to_hp_map = DrugMapper.make_meddra_to_hp_map(graph)
        hp_curie = DrugMapper.meddra_to_hp_map.get(medra_curie, None)
        if hp_curie is not None:
            ret_hp_set.add(hp_curie)
        return ret_hp_set

    @staticmethod
    def map_drug_to_UMLS(chembl_id):
        """
        mapping between a drug and UMLS ids corresponding to indications and contraindications

        :param chembl_id: The CHEMBL ID for a drug

        :return: A dictionary with two fields ('indication' and 'contraindication'). Each field is a set of strings
                containing the found UMLS ids or empty set if none were found
        """
        indication_umls_set = set()
        contraindication_umls_set = set()
        if not isinstance(chembl_id, str):
            return {'indications': indication_umls_set, "contraindications": contraindication_umls_set}
        drug_use = QueryMyChem.get_drug_use(chembl_id)
        indications = drug_use['indications']
        contraindications = drug_use['contraindications']

        sm = SynonymMapper()
        for indication in indications:
            if 'snomed_id' in indication.keys():
                oxo_result = sm.get_all_from_oxo('SNOMEDCT:' + indication['snomed_id'], ['UMLS'])
                if oxo_result is not None:
                    indication_umls_set.add(oxo_result[0])

        for contraindication in contraindications:
            if 'snomed_id' in contraindication.keys():
                oxo_result = sm.get_all_from_oxo('SNOMEDCT:' + contraindication['snomed_id'], ['UMLS'])
                if oxo_result is not None:
                    contraindication_umls_set.add(oxo_result[0])

        return {'indications': indication_umls_set, "contraindications": contraindication_umls_set}

        # tgt = QueryUMLS.get_ticket_gen()
        # for indication in indications:
        #     if 'snomed_name' in indication.keys():
        #         cui = QueryUMLS.get_cui_from_string_precision(indication['snomed_name'], tgt)
        #         if cui is None:
        #             print(indication['snomed_name'])
        #         else:
        #             print(cui)
        #             umls_set.add(cui)
        # return umls_set

    @staticmethod
    def map_drug_to_ontology(chembl_id):
        """
        mapping between a drug and Disease Ontology IDs and/or Human Phenotype Ontology IDs corresponding to indications

        :param chembl_id: The CHEMBL ID for a drug

        :return: A dictionary with two fields ('indication' and 'contraindication'). Each field is a set of strings
                containing the found hp / omim / doid ids or empty set if none were found
        """
        indication_onto_set = set()
        contraindication_onto_set = set()
        if not isinstance(chembl_id, str):
            return {'indications': indication_onto_set, "contraindications": contraindication_onto_set}
        drug_use = QueryMyChem.get_drug_use(chembl_id)
        indications = drug_use['indications']
        contraindications = drug_use['contraindications']
        sm = SynonymMapper()
        for indication in indications:
            if 'snomed_concept_id' in indication.keys():
                oxo_results = sm.get_all_from_oxo('SNOMEDCT:' + str(indication['snomed_concept_id']), ['DOID', 'OMIM', 'HP'])
                if oxo_results is not None:
                    for oxo_result in oxo_results:
                        indication_onto_set.add(oxo_result)
        for contraindication in contraindications:
            if 'snomed_concept_id' in contraindication.keys():
                oxo_results = sm.get_all_from_oxo('SNOMEDCT:' + str(contraindication['snomed_concept_id']), ['DOID', 'OMIM', 'HP'])
                if oxo_results is not None:
                    for oxo_result in oxo_results:
                        contraindication_onto_set.add(oxo_result)
        return {'indications': indication_onto_set, "contraindications": contraindication_onto_set}


if __name__ == '__main__':
    # requests_cache.install_cache('DrugMapper')
    # hp_set = DrugMapper.map_drug_to_hp_with_side_effects("KWHRDNMACVLHCE-UHFFFAOYSA-N")
    # print(hp_set)
    # print(len(hp_set))

    # start_time = time.time()
    hp_set = DrugMapper.map_drug_to_hp_with_side_effects("CHEMBL1082")
    print(hp_set)
    hp_set = DrugMapper.map_drug_to_hp_with_side_effects("CHEMBL112") # acetaminophen
    print(hp_set)
    hp_set = DrugMapper.map_drug_to_hp_with_side_effects("CHEMBL521") # ibuprofen
    print(hp_set)
    hp_set = DrugMapper.map_drug_to_hp_with_side_effects("CHEMBL1431") # ibuprofen
    print(hp_set)
    # print(len(hp_set))
    # print("--- %s seconds ---" % (time.time() - start_time))

    # umls_set = DrugMapper.map_drug_to_UMLS("CHEMBL1082")
    # print(umls_set)

    # onto_set = DrugMapper.map_drug_to_ontology("CHEMBL:521")
    # print(onto_set['contraindications'])

    # onto_set = DrugMapper.map_drug_to_ontology("CHEMBL2107884")
    # print(onto_set)

    # onto_set = DrugMapper.map_drug_to_ontology("CHEMBL8")
    # print(onto_set)

