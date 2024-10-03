from typing import List, Type, Tuple
from ai_haley_kg_domain.model.KGInteraction import KGInteraction
from kgraphservice.kgraph_service_inf import KGraphServiceInterface, KGFP, KGN, G
from kgraphservice.ontology.ontology_query_manager import OntologyQueryManager
from vital_ai_vitalsigns.query.part_list import PartList
from vital_ai_vitalsigns.query.result_list import ResultList
from vital_ai_vitalsigns.service.vital_namespace import VitalNamespace
from vital_ai_vitalsigns.service.vital_service_status import VitalServiceStatus


class KGServiceImpl(KGraphServiceInterface):
    def get_ontology_query_manager(self) -> OntologyQueryManager:
        pass

    def get_graph(self, graph_uri: str) -> VitalNamespace:
        pass

    def list_graphs(self) -> List[VitalNamespace]:
        pass

    def check_create_graph(self, graph_uri: str) -> bool:
        pass

    def create_graph(self, graph_uri: str) -> bool:
        pass

    def delete_graph(self, graph_uri: str) -> bool:
        pass

    def purge_graph(self, graph_uri: str) -> bool:
        pass

    def get_graph_all_objects(self, graph_uri: str, limit=100, offset=0) -> ResultList:
        pass

    def insert_object(self, graph_uri: str, graph_object: G) -> VitalServiceStatus:
        pass

    def insert_object_list(self, graph_uri: str, graph_object_list: List[G]) -> VitalServiceStatus:
        pass

    def update_object(self, graph_object: G, graph_uri: str, *, upsert: bool = False) -> VitalServiceStatus:
        pass

    def update_object_list(self, graph_object_list: List[G], graph_uri: str, *,
                           upsert: bool = False) -> VitalServiceStatus:
        pass

    def get_object(self, object_uri: str, graph_uri: str | None = None) -> G:
        pass

    def get_object_list(self, object_uri_list: List[str], graph_uri: str | None = None) -> ResultList:
        pass

    def delete_object(self, object_uri: str, graph_uri: str | None = None) -> VitalServiceStatus:
        pass

    def delete_object_list(self, object_uri_list: List[str], graph_uri: str | None = None) -> VitalServiceStatus:
        pass

    def filter_query(self, graph_uri: str, sparql_query: str) -> ResultList:
        pass

    def query(self, graph_uri: str, sparql_query: str) -> ResultList:
        pass

    def query_construct(self, graph_uri: str, sparql_query: str, binding_list: List[Tuple[str, str]]) -> ResultList:
        pass

    def get_interaction_list(self, graph_uri: str, limit=100, offset=0) -> ResultList:
        pass

    def get_interaction_graph(self, graph_uri: str, interaction: KGInteraction, limit=100, offset=0) -> ResultList:
        pass

    def get_interaction_frames(self, graph_uri: str, interaction: KGInteraction, limit=100, offset=0) -> PartList:
        pass

    def get_interaction_nodes(self, graph_uri: str, interaction: KGInteraction, kgnode_type: Type[KGN], limit=100,
                              offset=0) -> ResultList:
        pass

    def get_frame(self, graph_uri: str, frame_uri: str, limit=100, offset=0) -> KGFP:
        pass

    def get_frames(self, graph_uri: str, frame_uri_list: List[str], limit=100, offset=0) -> PartList:
        pass

    def get_frame_id(self, graph_uri: str, frame_id: str, limit=100, offset=0) -> KGFP:
        pass

    def get_frames_id(self, graph_uri: str, frame_id_list: List[str], limit=100, offset=0) -> PartList:
        pass

    def get_frames_root(self, graph_uri: str, root_uri: str, limit=100, offset=0) -> PartList:
        pass

    def get_graph_objects_type(self, graph_uri: str, class_uri: str, include_subclasses=True, limit=100,
                               offset=0) -> ResultList:
        pass

    def get_graph_objects_tag(self, graph_uri: str, kg_graph_uri: str, limit=100, offset=0) -> ResultList:
        pass

    def delete_frame(self, graph_uri: str, frame_uri: str) -> VitalServiceStatus:
        pass

    def delete_frames(self, graph_uri: str, frame_uri_list: List[str]) -> VitalServiceStatus:
        pass

    def delete_frame_id(self, graph_uri: str, frame_id: str) -> VitalServiceStatus:
        pass

    def delete_frames_id(self, graph_uri: str, frame_id_list: List[str]) -> VitalServiceStatus:
        pass

    def delete_graph_objects_tag(self, graph_uri: str, kg_graph_uri: str) -> VitalServiceStatus:
        pass

# kg service implementation, wraps around underlying
# kg service

# input to include details of agent and user making request
# include additional validation, constraints on queries, etc.

# special case for kg search of wikidata is covered
# in kgraphagent (wrapper) and kgraphservice
# kgservice interface may need to be extended or a construct query may be sufficient
# special namespace for wikidata?

