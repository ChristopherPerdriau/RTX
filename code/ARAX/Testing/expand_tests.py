#!/bin/env python3
import time
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__))+"/../ARAXQuery/")
from response import Response
from actions_parser import ActionsParser
from ARAX_messenger import ARAXMessenger
from ARAX_expander import ARAXExpander
from ARAX_resultify import ARAXResultify


# Utility functions

def run_query(actions_list, num_allowed_retries=2):
    response = Response()
    actions_parser = ActionsParser()

    # Parse the raw action_list into commands and parameters
    result = actions_parser.parse(actions_list)
    response.merge(result)
    if result.status != 'OK':
        print(response.show(level=Response.DEBUG))
        return response
    actions = result.data['actions']

    messenger = ARAXMessenger()
    expander = ARAXExpander()
    resultifier = ARAXResultify()

    # Run each action
    for action in actions:
        if action['command'] == 'create_message':
            result = messenger.create_message()
            message = result.data['message']
            response.data = result.data
        elif action['command'] == 'add_qnode':
            result = messenger.add_qnode(message, action['parameters'])
        elif action['command'] == 'add_qedge':
            result = messenger.add_qedge(message, action['parameters'])
        elif action['command'] == 'expand':
            result = expander.apply(message, action['parameters'])
        elif action['command'] == 'resultify':
            result = resultifier.apply(message, action['parameters'])
        elif action['command'] == 'return':
            break
        else:
            response.error(f"Unrecognized command {action['command']}", error_code="UnrecognizedCommand")
            print(response.show(level=Response.DEBUG))
            return None

        # Merge down this result and end if we're in an error state
        response.merge(result)
        if result.status != 'OK':
            # Try again if we ran into the intermittent neo4j connection issue (#649)
            if (result.error_code == 'ConnectionResetError' or result.error_code == 'OSError') and num_allowed_retries > 0:
                return run_query(actions_list, num_allowed_retries - 1)
            else:
                print(response.show(level=Response.DEBUG))
                return None

    # print(response.show(level=Response.DEBUG))
    kg_in_dict_form = convert_list_kg_to_dict_kg(message.knowledge_graph)
    print_counts_by_qgid(kg_in_dict_form)
    return kg_in_dict_form


def convert_list_kg_to_dict_kg(knowledge_graph):
    dict_kg = {'nodes': dict(), 'edges': dict()}
    for node in knowledge_graph.nodes:
        if node.qnode_id not in dict_kg['nodes']:
            dict_kg['nodes'][node.qnode_id] = dict()
        dict_kg['nodes'][node.qnode_id][node.id] = node
    for edge in knowledge_graph.edges:
        if edge.qedge_id not in dict_kg['edges']:
            dict_kg['edges'][edge.qedge_id] = dict()
        dict_kg['edges'][edge.qedge_id][edge.id] = edge
    return dict_kg


def conduct_standard_testing(kg_in_dict_form):
    check_for_orphans(kg_in_dict_form)


def print_counts_by_qgid(kg_in_dict_form):
    for qnode_id, corresponding_nodes in sorted(kg_in_dict_form['nodes'].items()):
        print(f"  {qnode_id}: {len(corresponding_nodes)}")
    for qedge_id, corresponding_edges in sorted(kg_in_dict_form['edges'].items()):
        print(f"  {qedge_id}: {len(corresponding_edges)}")


def print_nodes(kg_in_dict_form):
    for qnode_id, nodes in kg_in_dict_form['nodes'].items():
        for node_key, node in nodes.items():
            print(f"{node.qnode_id}, {node.type}, {node.id}, {node.name}")


def print_edges(kg_in_dict_form):
    for qedge_id, edges in kg_in_dict_form['edges'].items():
        for edge_key, edge in edges.items():
            print(f"{edge.qedge_id}, {edge.id}")


def print_passing_message(start_time=0.0):
    if start_time:
        print(f"  ...PASSED! (took {round(time.time() - start_time)} seconds)")
    else:
        print(f"  ...PASSED!")


def check_for_orphans(kg_in_dict_form):
    node_ids = set()
    node_ids_used_by_edges = set()
    for qnode_id, nodes in kg_in_dict_form['nodes'].items():
        for node_key, node in nodes.items():
            node_ids.add(node_key)
    for qedge_id, edges in kg_in_dict_form['edges'].items():
        for edge_key, edge in edges.items():
            node_ids_used_by_edges.add(edge.source_id)
            node_ids_used_by_edges.add(edge.target_id)
    assert node_ids == node_ids_used_by_edges or len(node_ids_used_by_edges) == 0


# Actual test cases

def test_kg1_parkinsons_demo_example():
    print("Testing KG1 parkinson's demo example")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=DOID:14330)",  # parkinson's
        "add_qnode(id=n01, type=protein, is_set=True)",
        "add_qnode(id=n02, type=chemical_substance)",
        "add_qedge(id=e00, source_id=n01, target_id=n00)",
        "add_qedge(id=e01, source_id=n01, target_id=n02, type=physically_interacts_with)",
        "expand(edge_id=[e00,e01], kp=ARAX/KG1, enforce_directionality=true)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    # Make sure only one node exists for n00 (the original curie)
    assert len(kg_in_dict_form['nodes']['n00']) == 1

    # Make sure all e00 edges map to Parkinson's curie for n00
    for edge_id, edge in kg_in_dict_form['edges']['e00'].items():
        assert edge.source_id == "DOID:14330" or edge.target_id == "DOID:14330"

    # Make sure all drugs returned are as expected
    for node_id, node in kg_in_dict_form['nodes']['n02'].items():
        assert "chemical_substance" in node.type

    # Make sure drugs include cilnidipine
    assert any(node.name.lower() == 'cilnidipine' for node in kg_in_dict_form['nodes']['n02'].values())

    # Make sure there are four proteins connecting to cilnidipine
    proteins_connected_to_cilnidipine = set()
    for edge_id, edge in kg_in_dict_form['edges']['e01'].items():
        if edge.source_id == "CHEMBL.COMPOUND:CHEMBL452076" or edge.target_id == "CHEMBL.COMPOUND:CHEMBL452076":
            non_cilnidipine_node = edge.source_id if edge.source_id != "CHEMBL.COMPOUND:CHEMBL452076" else edge.target_id
            proteins_connected_to_cilnidipine.add(non_cilnidipine_node)
    assert(len(proteins_connected_to_cilnidipine) >= 4)

    print_passing_message()


def test_kg2_parkinsons_demo_example():
    print("Testing KG2 parkinson's demo example")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=DOID:14330)",  # parkinson's
        "add_qnode(id=n01, type=protein, is_set=True)",
        "add_qnode(id=n02, type=chemical_substance)",
        "add_qedge(id=e00, source_id=n01, target_id=n00)",
        "add_qedge(id=e01, source_id=n01, target_id=n02, type=molecularly_interacts_with)",
        "expand(edge_id=[e00,e01], kp=ARAX/KG2, enforce_directionality=true, use_synonyms=false)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    # Make sure only one node exists for n00 (the original curie)
    assert len(kg_in_dict_form['nodes']['n00']) == 1

    # Make sure all e00 edges map to Parkinson's curie for n00
    for edge_id, edge in kg_in_dict_form['edges']['e00'].items():
        assert edge.source_id == "DOID:14330" or edge.target_id == "DOID:14330"

    # Make sure all drugs returned are as expected
    for node_id, node in kg_in_dict_form['nodes']['n02'].items():
        assert "chemical_substance" in node.type

    # Make sure drugs include cilnidipine
    assert any(node.name.lower() == 'cilnidipine' for node in kg_in_dict_form['nodes']['n02'].values())

    # Make sure there are four proteins connecting to cilnidipine
    proteins_connected_to_cilnidipine = set()
    for edge_id, edge in kg_in_dict_form['edges']['e01'].items():
        if edge.source_id == "CHEMBL.COMPOUND:CHEMBL452076" or edge.target_id == "CHEMBL.COMPOUND:CHEMBL452076":
            non_cilnidipine_node = edge.source_id if edge.source_id != "CHEMBL.COMPOUND:CHEMBL452076" else edge.target_id
            proteins_connected_to_cilnidipine.add(non_cilnidipine_node)
    assert(len(proteins_connected_to_cilnidipine) >= 4)

    assert len(kg_in_dict_form['nodes']['n00']) == 1
    assert len(kg_in_dict_form['nodes']['n01']) == 18
    assert len(kg_in_dict_form['nodes']['n02']) == 1119
    assert len(kg_in_dict_form['edges']['e00']) == 18
    assert len(kg_in_dict_form['edges']['e01']) == 1871

    print_passing_message()


def test_kg2_synonym_map_back_parkinsons_proteins():
    print("Testing kg2 synonym map back parkinsons proteins")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=DOID:14330)",  # parkinson's
        "add_qnode(id=n01, type=protein, is_set=True)",
        "add_qedge(id=e00, source_id=n01, target_id=n00)",
        "expand(edge_id=e00, kp=ARAX/KG2)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    # Make sure all edges have been remapped to original curie for n00
    for edge_key, edge in kg_in_dict_form['edges']['e00'].items():
        assert edge.source_id == "DOID:14330" or edge.target_id == "DOID:14330"

    # Make sure only one node exists for n00 (the original curie)
    assert len(kg_in_dict_form['nodes']['n00']) == 1

    # Take a look at the proteins returned, make sure they're all proteins
    for node_key, node in kg_in_dict_form['nodes']['n01'].items():
        assert "protein" in node.type

    print_passing_message()


def test_kg2_synonym_map_back_parkinsons_full_example():
    print("Testing kg2 synonym map back parkinsons full example")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=DOID:14330)",  # parkinson's
        "add_qnode(id=n01, type=protein, is_set=True)",
        "add_qnode(id=n02, type=chemical_substance)",
        "add_qedge(id=e00, source_id=n01, target_id=n00)",
        "add_qedge(id=e01, source_id=n01, target_id=n02, type=molecularly_interacts_with)",
        "expand(edge_id=[e00,e01], kp=ARAX/KG2)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    # Make sure only one node exists for n00 (the original curie)
    assert len(kg_in_dict_form['nodes']['n00']) == 1

    # Make sure all e00 edges have been remapped to original curie for n00
    for edge_id, edge in kg_in_dict_form['edges']['e00'].items():
        assert edge.source_id == "DOID:14330" or edge.target_id == "DOID:14330"

    # Make sure all drugs returned are as expected
    for node_id, node in kg_in_dict_form['nodes']['n02'].items():
        assert "chemical_substance" in node.type

    print_passing_message()


def test_kg2_synonym_add_all_parkinsons_full_example():
    print("Testing kg2 synonym add all parkinson's full example")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=DOID:14330)",  # parkinson's
        "add_qnode(id=n01, type=protein, is_set=True)",
        "add_qnode(id=n02, type=chemical_substance)",
        "add_qedge(id=e00, source_id=n01, target_id=n00)",
        "add_qedge(id=e01, source_id=n01, target_id=n02, type=molecularly_interacts_with)",
        "expand(edge_id=[e00,e01], kp=ARAX/KG2, synonym_handling=add_all)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    # Make sure all drugs returned are as expected
    for node_id, node in kg_in_dict_form['nodes']['n02'].items():
        assert "chemical_substance" in node.type

    print_passing_message()


def test_demo_example_1_simple():
    print(f"Testing demo example 1 (Acetaminophen) without synonyms, using KG1")
    actions_list = [
        "create_message",
        "add_qnode(name=acetaminophen, id=n0)",
        "add_qnode(type=protein, id=n1)",
        "add_qedge(source_id=n0, target_id=n1, id=e0)",
        "expand(edge_id=e0, use_synonyms=false)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    assert len(kg_in_dict_form['nodes']['n0']) >= 1
    assert len(kg_in_dict_form['nodes']['n1']) >= 32
    assert len(kg_in_dict_form['edges']['e0']) >= 64

    print_passing_message()


def test_demo_example_2_simple():
    print(f"Testing demo example 2 (Parkinson's) without synonyms, using KG1")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=DOID:14330)",  # parkinson's
        "add_qnode(id=n01, type=protein, is_set=True)",
        "add_qnode(id=n02, type=chemical_substance)",
        "add_qedge(id=e00, source_id=n01, target_id=n00)",
        "add_qedge(id=e01, source_id=n01, target_id=n02, type=physically_interacts_with)",
        "expand(edge_id=[e00,e01], kp=ARAX/KG1, use_synonyms=false)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    assert len(kg_in_dict_form['nodes']['n00']) >= 1
    assert len(kg_in_dict_form['nodes']['n01']) >= 18
    assert len(kg_in_dict_form['nodes']['n02']) >= 1119
    assert len(kg_in_dict_form['edges']['e00']) >= 18
    assert len(kg_in_dict_form['edges']['e01']) >= 1871

    print_passing_message()


def test_demo_example_3_simple():
    print(f"Testing demo example 3 (hypopituitarism) without synonyms, using KG1")
    actions_list = [
        "create_message",
        "add_qnode(curie=DOID:9406, id=n00)",
        "add_qnode(type=chemical_substance, is_set=true, id=n01)",
        "add_qnode(type=protein, id=n02)",
        "add_qedge(source_id=n00, target_id=n01, id=e00)",
        "add_qedge(source_id=n01, target_id=n02, id=e01)",
        "expand(edge_id=[e00,e01], use_synonyms=false)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    assert len(kg_in_dict_form['nodes']['n00']) >= 1
    assert len(kg_in_dict_form['nodes']['n01']) >= 29
    assert len(kg_in_dict_form['nodes']['n02']) >= 240
    assert len(kg_in_dict_form['edges']['e00']) >= 29
    assert len(kg_in_dict_form['edges']['e01']) >= 1368

    print_passing_message()


def test_demo_example_1_with_synonyms():
    print(f"Testing demo example 1 (Acetaminophen) WITH synonyms, using KG1")
    actions_list = [
        "create_message",
        "add_qnode(name=acetaminophen, id=n0)",
        "add_qnode(type=protein, id=n1)",
        "add_qedge(source_id=n0, target_id=n1, id=e0)",
        "expand(edge_id=e0)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    assert len(kg_in_dict_form['nodes']['n0']) >= 1
    assert len(kg_in_dict_form['nodes']['n1']) >= 32
    assert len(kg_in_dict_form['edges']['e0']) >= 64

    print_passing_message()


def test_demo_example_2_with_synonyms():
    print(f"Testing demo example 2 (Parkinson's) WITH synonyms, using KG1")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=DOID:14330)",  # parkinson's
        "add_qnode(id=n01, type=protein, is_set=True)",
        "add_qnode(id=n02, type=chemical_substance)",
        "add_qedge(id=e00, source_id=n01, target_id=n00)",
        "add_qedge(id=e01, source_id=n01, target_id=n02, type=physically_interacts_with)",
        "expand(edge_id=[e00,e01], kp=ARAX/KG1)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    assert len(kg_in_dict_form['nodes']['n00']) >= 1
    assert len(kg_in_dict_form['nodes']['n01']) >= 18
    assert len(kg_in_dict_form['nodes']['n02']) >= 1119
    assert len(kg_in_dict_form['edges']['e00']) >= 18
    assert len(kg_in_dict_form['edges']['e01']) >= 1871

    print_passing_message()


def test_demo_example_3_with_synonyms():
    print(f"Testing demo example 3 (hypopituitarism) WITH synonyms, using KG1")
    actions_list = [
        "create_message",
        "add_qnode(curie=DOID:9406, id=n00)",
        "add_qnode(type=chemical_substance, is_set=true, id=n01)",
        "add_qnode(type=protein, id=n02)",
        "add_qedge(source_id=n00, target_id=n01, id=e00)",
        "add_qedge(source_id=n01, target_id=n02, id=e01)",
        "expand(edge_id=[e00,e01])",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    assert len(kg_in_dict_form['nodes']['n00']) >= 1
    assert len(kg_in_dict_form['nodes']['n01']) >= 29
    assert len(kg_in_dict_form['nodes']['n02']) >= 240
    assert len(kg_in_dict_form['edges']['e00']) >= 29
    assert len(kg_in_dict_form['edges']['e01']) >= 1368

    print_passing_message()


def erics_first_kg1_synonym_test_without_synonyms():
    print(f"Testing Eric's first KG1 synonym test without synonyms")
    actions_list = [
        "create_message",
        "add_qnode(name=PHENYLKETONURIA, id=n00)",
        "add_qnode(id=n01)",
        "add_qedge(source_id=n00, target_id=n01, id=e00)",
        "expand(edge_id=e00, kp=ARAX/KG1, use_synonyms=false)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    print_passing_message()


def erics_first_kg1_synonym_test_with_synonyms():
    print(f"Testing Eric's first KG1 synonym test WITH synonyms")
    actions_list = [
        "create_message",
        "add_qnode(name=PHENYLKETONURIA, id=n00)",
        "add_qnode(id=n01)",
        "add_qedge(source_id=n00, target_id=n01, id=e00)",
        "expand(edge_id=e00, kp=ARAX/KG1)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    print_passing_message()


def acetaminophen_example_enforcing_directionality():
    print(f"Testing acetaminophen example with enforced directionality")
    actions_list = [
        "create_message",
        "add_qnode(name=acetaminophen, id=n00)",
        "add_qnode(type=protein, id=n01)",
        "add_qedge(source_id=n00, target_id=n01, id=e00)",
        "expand(edge_id=e00, use_synonyms=false, enforce_directionality=true)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    assert len(kg_in_dict_form['nodes']['n00']) == 1
    assert len(kg_in_dict_form['nodes']['n01']) == 32
    assert len(kg_in_dict_form['edges']['e00']) == 32

    # Make sure the source of every node is acetaminophen
    for node_id in kg_in_dict_form['nodes']['n00'].keys():
        assert node_id == "CHEMBL.COMPOUND:CHEMBL112"

    print_passing_message()


def parkinsons_example_enforcing_directionality():
    print(f"Testing Parkinson's using KG1, enforcing directionality")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=DOID:14330)",  # parkinson's
        "add_qnode(id=n01, type=protein, is_set=True)",
        "add_qnode(id=n02, type=chemical_substance)",
        "add_qedge(id=e00, source_id=n01, target_id=n00)",
        "add_qedge(id=e01, source_id=n01, target_id=n02, type=physically_interacts_with)",
        "expand(edge_id=[e00,e01], kp=ARAX/KG1, enforce_directionality=true)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    assert len(kg_in_dict_form['nodes']['n00']) == 1
    assert len(kg_in_dict_form['nodes']['n01']) == 18
    assert len(kg_in_dict_form['nodes']['n02']) == 1119
    assert len(kg_in_dict_form['edges']['e00']) == 18
    assert len(kg_in_dict_form['edges']['e01']) == 1871

    print_passing_message()


def ambitious_query_causing_multiple_qnode_ids_error():
    print(f"Testing ambitious query causing multiple qnode_ids error (#720)")
    start = time.time()
    actions_list = [
        "create_message",
        "add_qnode(curie=DOID:14330, id=n00)",
        "add_qnode(is_set=true, id=n01)",
        "add_qnode(type=disease, id=n02)",
        "add_qedge(source_id=n00, target_id=n01, id=e00)",
        "add_qedge(source_id=n01, target_id=n02, id=e01)",
        "expand(edge_id=[e00, e01])",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    print_passing_message(start)


def test_kg1_property_format():
    print(f"Testing kg1 property format")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=DOID:14330)",  # parkinson's
        "add_qnode(id=n01, type=protein, is_set=True)",
        "add_qnode(id=n02, type=chemical_substance)",
        "add_qedge(id=e00, source_id=n01, target_id=n00)",
        "add_qedge(id=e01, source_id=n01, target_id=n02, type=physically_interacts_with)",
        "expand(edge_id=[e00,e01], kp=ARAX/KG1)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    for qnode_id, nodes in kg_in_dict_form['nodes'].items():
        for node in nodes.values():
            assert type(node.name) is str
            assert type(node.id) is str
            assert ":" in node.id
            assert type(node.qnode_id) is str
            assert type(node.type) is list
            assert type(node.uri) is str

    for qedge_id, edges in kg_in_dict_form['edges'].items():
        for edge in edges.values():
            assert type(edge.id) is str
            assert type(edge.is_defined_by) is str
            assert type(edge.provided_by) is str
            assert type(edge.qedge_id) is str
            assert type(edge.type) is str
            if "chembl" in edge.provided_by.lower():
                assert edge.edge_attributes[0].name == "probability"

    print_passing_message()


def simple_bte_acetaminophen_query():
    print(f"Testing simple BTE acetaminophen query")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=CHEMBL.COMPOUND:CHEMBL112)",
        "add_qnode(id=n01, type=protein, is_set=True)",
        "add_qedge(id=e00, source_id=n01, target_id=n00)",
        "expand(edge_id=e00, kp=BTE)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    print_passing_message()


def simple_bte_cdk2_query():
    print(f"Testing simple BTE CDK2 query")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=NCBIGene:1017)",
        "add_qnode(id=n01, type=chemical_substance, is_set=True)",
        "add_qedge(id=e00, source_id=n01, target_id=n00, type=targetedBy)",
        "expand(edge_id=e00, kp=BTE)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    print_passing_message()


def test_two_hop_bte_query():
    print(f"Testing two-hop BTE query")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=NCBIGene:1017)",
        "add_qnode(id=n01, type=protein, is_set=True)",
        "add_qnode(id=n02, type=gene)",
        "add_qedge(id=e00, source_id=n01, target_id=n00)",
        "add_qedge(id=e01, source_id=n01, target_id=n02)",
        "expand(edge_id=[e00, e01], kp=BTE)",
        "return(message=true, store=false)",
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    print_passing_message()


def test_simple_bidirectional_query():
    print(f"Testing simple bidirectional query (caused #727)")
    actions_list = [
        "create_message",
        "add_qnode(name=CHEMBL.COMPOUND:CHEMBL1276308, id=n00)",
        "add_qnode(type=protein, id=n01)",
        "add_qedge(source_id=n00, target_id=n01, id=e00)",
        "expand(edge_id=e00)",
        "return(message=true, store=false)"
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    print_passing_message()


def query_that_doesnt_return_original_curie():
    print(f"Testing query that doesn't return the original curie (only synonym curies - #731)")
    actions_list = [
        "create_message",
        "add_qnode(name=MONDO:0005737, id=n0, type=disease)",
        "add_qnode(type=protein, id=n1)",
        "add_qnode(type=disease, id=n2)",
        "add_qedge(source_id=n0, target_id=n1, id=e0)",
        "add_qedge(source_id=n1, target_id=n2, id=e1)",
        "expand(edge_id=[e0,e1], kp=ARAX/KG2)",
        "return(message=true, store=false)"
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)

    assert len(kg_in_dict_form['nodes']['n0']) == 1
    assert "MONDO:0005737" in kg_in_dict_form['nodes']['n0']

    for edge in kg_in_dict_form['edges']['e0'].values():
        assert edge.source_id == "MONDO:0005737" or edge.target_id == "MONDO:0005737"

    print_passing_message()


def single_node_query_map_back():
    print("Testing a single node query (clopidogrel) using KG2, with map_back synonym handling")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=CHEMBL.COMPOUND:CHEMBL1771)",
        "expand(node_id=n00, kp=ARAX/KG2, synonym_handling=map_back)",
        "return(message=true, store=false)"
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)
    assert len(kg_in_dict_form['nodes']['n00']) == 1
    assert kg_in_dict_form['nodes']['n00'].get("CHEMBL.COMPOUND:CHEMBL1771")
    print_passing_message()


def single_node_query_add_all():
    print("Testing a single node query (clopidogrel) using KG2, with add_all synonym handling")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=CHEMBL.COMPOUND:CHEMBL1771)",
        "expand(node_id=n00, kp=ARAX/KG2, synonym_handling=add_all)",
        "return(message=true, store=false)"
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)
    assert len(kg_in_dict_form['nodes']['n00']) > 1
    assert "CHEMBL.COMPOUND:CHEMBL1771" in kg_in_dict_form['nodes']['n00']
    print_passing_message()


def single_node_query_without_synonyms():
    print("Testing a single node query without using synonyms")
    actions_list = [
        "create_message",
        "add_qnode(id=n00, curie=CHEMBL.COMPOUND:CHEMBL1276308)",
        "expand(kp=ARAX/KG1, use_synonyms=false)",
        "return(message=true, store=false)"
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)
    assert len(kg_in_dict_form['nodes']['n00']) == 1
    assert "CHEMBL.COMPOUND:CHEMBL1276308" in kg_in_dict_form['nodes']['n00']
    print_passing_message()


def query_with_no_edge_or_node_ids():
    print("Testing query with no edge or node IDs specified")
    actions_list = [
        "create_message",
        "add_qnode(name=CHEMBL.COMPOUND:CHEMBL1276308, id=n00)",
        "add_qnode(type=protein, id=n01)",
        "add_qedge(source_id=n00, target_id=n01, id=e00)",
        "expand()",
        "return(message=true, store=false)"
    ]
    kg_in_dict_form = run_query(actions_list)
    conduct_standard_testing(kg_in_dict_form)
    assert kg_in_dict_form['nodes']['n00'] and kg_in_dict_form['nodes']['n01'] and kg_in_dict_form['edges']['e00']
    print_passing_message()


def main():
    # Regular tests
    test_kg1_parkinsons_demo_example()
    test_kg2_parkinsons_demo_example()
    test_kg2_synonym_map_back_parkinsons_proteins()
    test_kg2_synonym_map_back_parkinsons_full_example()
    test_kg2_synonym_add_all_parkinsons_full_example()
    test_demo_example_1_simple()
    test_demo_example_2_simple()
    test_demo_example_3_simple()
    test_demo_example_1_with_synonyms()
    test_demo_example_2_with_synonyms()
    test_demo_example_3_with_synonyms()
    erics_first_kg1_synonym_test_without_synonyms()
    erics_first_kg1_synonym_test_with_synonyms()
    acetaminophen_example_enforcing_directionality()
    parkinsons_example_enforcing_directionality()
    test_kg1_property_format()
    simple_bte_acetaminophen_query()
    simple_bte_cdk2_query()
    test_two_hop_bte_query()
    test_simple_bidirectional_query()
    query_that_doesnt_return_original_curie()
    single_node_query_map_back()
    single_node_query_add_all()
    single_node_query_without_synonyms()
    query_with_no_edge_or_node_ids()

    # Bug tests
    # ambitious_query_causing_multiple_qnode_ids_error()

    print(f'\nEVERYTHING PASSED!')


if __name__ == "__main__":
    main()
