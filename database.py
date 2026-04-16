"""
Neo4j database driver and query execution.
Implements Query A, B, C from the LLM_QUERY_PIPELINE_GUIDE.md
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase, Session, Driver
from neo4j.graph import Node, Relationship, Path

logger = logging.getLogger(__name__)

class Neo4jDatabase:
    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j"):
        self.uri = uri
        self.username = username
        self.password = password
        self.database = database
        self.driver: Optional[Driver] = None
        self.query_timeout_seconds = float(os.getenv("NEO4J_QUERY_TIMEOUT_SECONDS", "20"))
        self.max_result_rows = int(os.getenv("NEO4J_MAX_RESULT_ROWS", "500"))
        self._identifier_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

    def _validate_entity_type(self, entity_type: str) -> str:
        """Validate Neo4j label names used in dynamic Cypher fragments."""
        value = (entity_type or "").strip()
        if not value or not self._identifier_pattern.fullmatch(value):
            raise ValueError("Invalid entity_type. Use alphanumeric/underscore label names only.")
        return value

    def _validate_property_names(self, properties: List[str]) -> List[str]:
        """Validate property identifiers before embedding in Cypher."""
        valid_props: List[str] = []
        for prop in properties:
            prop_name = (prop or "").strip()
            if not prop_name or not self._identifier_pattern.fullmatch(prop_name):
                raise ValueError(f"Invalid property name: {prop}")
            valid_props.append(prop_name)
        return valid_props
    
    def connect(self):
        """Establish connection to Neo4j."""
        try:
            driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password)
            )
            self.driver = driver
            # Test connection
            with driver.session(database=self.database) as session:
                result = session.run("RETURN 1")
                result.consume()
            print("✅ Connected to Neo4j Aura")
        except Exception as e:
            print(f"❌ Failed to connect to Neo4j: {e}")
            raise
    
    def close(self):
        """Close connection."""
        if self.driver:
            self.driver.close()

    def _get_driver(self) -> Driver:
        """Return initialized driver or raise a clear error."""
        if not self.driver:
            raise ValueError("Database driver is not connected. Call connect() before executing queries.")
        return self.driver
    
    def query_all_entities(self, entity_type: str = "UpstreamProducer") -> List[Dict[str, Any]]:
        """
        Query A: List all entities (used in pipeline Step 3)
        Returns: [{id, name, short_name}, ...]
        """
        entity_label = self._validate_entity_type(entity_type)
        cypher = f"""
        MATCH (n:{entity_label})
        RETURN {{
            id: n.id,
            name: n.name,
            short_name: COALESCE(n.short_name, n.name)
        }} as entity
        ORDER BY entity.name
        """
        
        with self._get_driver().session(database=self.database) as session:
            result = session.run(cypher)
            entities = [record["entity"] for record in result]
            return entities
    
    def discover_properties(self, entity_id: str, entity_type: str = "UpstreamProducer") -> Dict[str, str]:
        """
        Query B: Discover what properties exist on an entity (used in pipeline Step 5)
        Returns: {property_name: property_type, ...}
        """
        try:
            entity_label = self._validate_entity_type(entity_type)
            # Simple approach: ask Neo4j what properties this entity has
            cypher = f"""
            MATCH (n:{entity_label}) WHERE n.id = $entity_id
            RETURN keys(n) as property_names
            """
            
            with self._get_driver().session(database=self.database) as session:
                result = session.run(cypher, entity_id=entity_id)
                record = result.single()
                
                if not record:
                    return {}
                
                property_names = record.get("property_names")
                
                if not property_names or not isinstance(property_names, list):
                    return {}
                
                # For each property, determine its type by querying a sample value
                property_types = {}
                
                cypher_get_values = f"""
                MATCH (n:{entity_label}) WHERE n.id = $entity_id
                RETURN n
                """
                
                result2 = session.run(cypher_get_values, entity_id=entity_id)
                node_record = result2.single()
                
                if node_record:
                    # Get the node as a dict-like object
                    try:
                        node = node_record[0] if len(node_record) > 0 else node_record
                    except (IndexError, TypeError):
                        node = node_record
                    
                    # Go through each property and determine its type
                    for prop_name in property_names:
                        try:
                            # Try to get the value from the node
                            prop_value = node.get(prop_name) if hasattr(node, 'get') else node[prop_name]
                            
                            if prop_value is None:
                                property_types[prop_name] = "NULL"
                            elif isinstance(prop_value, bool):
                                property_types[prop_name] = "BOOLEAN"
                            elif isinstance(prop_value, int):
                                property_types[prop_name] = "INTEGER"
                            elif isinstance(prop_value, float):
                                property_types[prop_name] = "FLOAT"
                            elif isinstance(prop_value, str):
                                property_types[prop_name] = "STRING"
                            elif isinstance(prop_value, list):
                                property_types[prop_name] = "LIST"
                            else:
                                property_types[prop_name] = "OTHER"
                        except (KeyError, TypeError, AttributeError):
                            property_types[prop_name] = "UNKNOWN"
                
                return property_types
        
        except Exception as e:
            print(f"Error discovering properties for {entity_id}: {e}")
            return {}
    
    def retrieve_entity_data(
        self,
        entity_id: str,
        properties: List[str],
        entity_type: str = "UpstreamProducer"
    ) -> Dict[str, Any]:
        """
        Query C: Retrieve specific properties from an entity (used in pipeline Step 7)
        Properties: list of property names to retrieve
        Returns: {property_name: value, ...}
        """
        if not properties:
            return {}

        entity_label = self._validate_entity_type(entity_type)
        safe_properties = self._validate_property_names(properties)
        
        # Build dynamic property list for Cypher - use map syntax {key: n.key}
        property_map = ", ".join([f"{prop}: n.{prop}" for prop in safe_properties])
        cypher = f"""
        MATCH (n:{entity_label}) WHERE n.id = $entity_id
        RETURN {{{property_map}}} as result
        """
        
        with self._get_driver().session(database=self.database) as session:
            result = session.run(cypher, entity_id=entity_id)
            record = result.single()
            
            if not record:
                return {}
            
            # Extract the result map from the record
            try:
                result_data = record.get("result") if hasattr(record, 'get') else record[0]
                if isinstance(result_data, dict):
                    return result_data
                else:
                    # Try to convert to dict if it's a Neo4j object
                    return dict(result_data) if result_data else {}
            except Exception as e:
                print(f"Error extracting result data: {e}")
                return {}
    
    def search_entities_by_keyword(
        self,
        keyword: str,
        entity_type: str = "UpstreamProducer"
    ) -> List[Dict[str, Any]]:
        """
        Search for entities by name or short_name (case-insensitive).
        Used for entity matching in pipeline Step 4.
        """
        entity_label = self._validate_entity_type(entity_type)
        keyword_lower = keyword.lower()
        
        cypher = f"""
        MATCH (n:{entity_label})
        WHERE LOWER(n.name) CONTAINS $keyword OR LOWER(COALESCE(n.short_name, '')) CONTAINS $keyword
        RETURN {{
            id: n.id,
            name: n.name,
            short_name: COALESCE(n.short_name, n.name)
        }} as entity
        ORDER BY entity.name
        """
        
        with self._get_driver().session(database=self.database) as session:
            result = session.run(cypher, keyword=keyword_lower)
            entities = [record["entity"] for record in result]
            return entities
    
    def get_entity_by_id(self, entity_id: str, entity_type: str = "UpstreamProducer") -> Optional[Dict[str, Any]]:
        """Get full entity record by ID."""
        entity_label = self._validate_entity_type(entity_type)
        cypher = f"""
        MATCH (n:{entity_label}) WHERE n.id = $entity_id
        RETURN {{
            id: n.id,
            name: n.name,
            short_name: COALESCE(n.short_name, n.name)
        }} as entity
        """
        
        with self._get_driver().session(database=self.database) as session:
            result = session.run(cypher, entity_id=entity_id)
            record = result.single()
            
            if record:
                return record["entity"]
            return None

    @staticmethod
    def _validate_read_only_cypher(cypher_query: str) -> None:
        """Reject non-read Cypher before execution."""
        normalized = cypher_query.strip()
        if not normalized:
            raise ValueError("Cypher query cannot be empty")

        # Disallow multi-statement queries and comment-based obfuscation.
        if ";" in normalized:
            raise ValueError("Multiple Cypher statements are not allowed")
        if "--" in normalized or "/*" in normalized or "*/" in normalized:
            raise ValueError("Cypher comments are not allowed in generated queries")

        query_upper = normalized.upper()

        forbidden_patterns = [
            r"\bCREATE\b",
            r"\bDELETE\b",
            r"\bDETACH\b",
            r"\bMERGE\b",
            r"\bSET\b",
            r"\bREMOVE\b",
            r"\bDROP\b",
            r"\bALTER\b",
            r"\bCALL\b",
            r"\bFOREACH\b",
            r"\bLOAD\s+CSV\b",
        ]

        for pattern in forbidden_patterns:
            if re.search(pattern, query_upper):
                raise ValueError(
                    "Query contains non-read operation. Allowed clauses are read-only: "
                    "MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY, LIMIT, "
                    "COUNT, COLLECT, DISTINCT, UNWIND."
                )

        starts_valid = re.match(r"^(MATCH|OPTIONAL\s+MATCH|WITH|UNWIND|RETURN)\b", query_upper)
        if not starts_valid:
            raise ValueError(
                "Query must start with one of: MATCH, OPTIONAL MATCH, WITH, UNWIND, RETURN"
            )

        # Guard against unbounded scans for non-aggregate queries.
        aggregate_tokens = ["COUNT(", "SUM(", "AVG(", "MIN(", "MAX(", "COLLECT("]
        has_aggregate = any(token in query_upper for token in aggregate_tokens)
        has_limit = "LIMIT" in query_upper
        if not has_aggregate and not has_limit:
            raise ValueError("Non-aggregate queries must include LIMIT for safety")

    def _serialize_value(self, value: Any) -> Any:
        """Convert Neo4j values into JSON-safe Python objects."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, list):
            return [self._serialize_value(item) for item in value]

        if isinstance(value, dict):
            return {key: self._serialize_value(val) for key, val in value.items()}

        if isinstance(value, Node):
            node_dict = dict(value)
            node_dict["_labels"] = list(value.labels)
            node_dict["_element_id"] = value.element_id
            return {key: self._serialize_value(val) for key, val in node_dict.items()}

        if isinstance(value, Relationship):
            rel_dict = dict(value)
            rel_dict["_type"] = value.type
            rel_dict["_element_id"] = value.element_id
            rel_dict["_start_node_id"] = value.start_node.element_id
            rel_dict["_end_node_id"] = value.end_node.element_id
            return {key: self._serialize_value(val) for key, val in rel_dict.items()}

        if isinstance(value, Path):
            return {
                "nodes": [self._serialize_value(node) for node in value.nodes],
                "relationships": [self._serialize_value(rel) for rel in value.relationships],
            }

        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                pass

        return str(value)

    def execute_raw_cypher(self, cypher_query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute an LLM-generated Cypher query after strict read-only validation.

        Args:
            cypher_query: Cypher query string
            parameters: Optional query parameters

        Returns:
            JSON-safe list of records
        """
        self._validate_read_only_cypher(cypher_query)

        if parameters is None:
            parameters = {}

        if not self.driver:
            raise ValueError("Database driver is not connected. Call connect() before executing queries.")

        try:
            with self._get_driver().session(database=self.database) as session:
                result = session.run(cypher_query, parameters, timeout=self.query_timeout_seconds)
                records: List[Dict[str, Any]] = []
                for record in result:
                    if len(records) >= self.max_result_rows:
                        logger.warning(
                            "Result row limit reached (%d). Truncating returned records.",
                            self.max_result_rows,
                        )
                        break
                    records.append({key: self._serialize_value(val) for key, val in dict(record).items()})
                return records
        except Exception as e:
            raise ValueError(f"Cypher execution error: {str(e)}")
    
    def execute_read_only_cypher(self, cypher_query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Backwards-compatible alias for execute_raw_cypher.
        """
        return self.execute_raw_cypher(cypher_query, parameters)


# Initialize database connection
db = Neo4jDatabase(
    uri=os.getenv("NEO4J_URI", "neo4j+s://0d8a4c43.databases.neo4j.io"),
    username=os.getenv("NEO4J_USERNAME", "neo4j"),
    password=os.getenv("NEO4J_PASSWORD", ""),
    database=os.getenv("NEO4J_DATABASE", "neo4j")
)
