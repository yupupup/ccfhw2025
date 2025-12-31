from typing import List, Any, Optional

class Parameter:
    """
    Represents a single configuration parameter.
    """
    def __init__(self, name: str, type: str, default: Any, min: Optional[int] = None, max: Optional[int] = None, id: Optional[int] = None):
        self.name = name
        self.type = type
        self.default = default
        self.min = min
        self.max = max
        self.id = id
    
    def __str__(self):
        return f"{self.name}: {self.type} (default: {self.default}, min: {self.min}, max: {self.max})"

    def is_bool(self):
        return self.type == "boolean"

    def is_int(self):
        return self.type == "integer"

    def get_test_values(self) -> List[Any]:
        """
        Generates test values based on parameter type and default value.
        """
        if self.is_bool():
            return [True, False]
        
        if self.is_int():
            try:
                v = int(self.default)
                if v == 0:
                    return [0, 1, 2, 4]
                elif v > 2147483648:
                    return []
                else:
                    # Ensure values are non-negative and integers
                    return sorted(list(set([
                        max(0, int(v / 2)), 
                        v, 
                        int(v * 1.5), 
                        v * 2
                    ])))
            except (ValueError, TypeError):
                return []

        if self.type == "float":
            try:
                v = float(self.default)
                if v == 0.0:
                    return [0.0, 0.1, 0.5, 1.0]
                return sorted(list(set([
                    max(0.0, v * 0.5),
                    v,
                    v * 1.5,
                    v * 2.0
                ])))
            except (ValueError, TypeError):
                return []

        return []

class ParameterRelationship:
    def __init__(self, src: str, target: str, type: str, target_value: Any = None):
        self.src = src
        self.target = target
        self.type = type
        self.target_value = target_value

class ParameterSpace:
    """
    Represents a collection of parameters and their relationships.
    """
    def __init__(self, parameters: List[Parameter], relationships: List[ParameterRelationship] = None):
        self.parameters = parameters
        self.relationships = relationships if relationships else []
        self._param_map = {p.name: p for p in parameters}

    def load_relationships_from_db(self, conn):
        """
        Loads parameter relationships from the database.
        """
        if not conn:
            return

        param_id_map = {p.id: p.name for p in self.parameters if p.id is not None}
        
        query = """
            SELECT source_parameter_id, target_parameter_id, relationship_type, value
            FROM parameter_relationships;
        """
        
        try:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                for row in rows:
                    src_id, target_id, rel_type, value = row
                    src_name = param_id_map.get(src_id)
                    target_name = param_id_map.get(target_id)
                    
                    if src_name and target_name:
                        # Parse value
                        target_value = value
                        if target_value is not None:
                            if str(target_value).lower() == 'true': target_value = True
                            elif str(target_value).lower() == 'false': target_value = False
                            else:
                                try:
                                    target_value = int(target_value)
                                except:
                                    try:
                                        target_value = float(target_value)
                                    except:
                                        pass

                        self.relationships.append(ParameterRelationship(src_name, target_name, rel_type, target_value))
            print(f"Loaded {len(self.relationships)} parameter relationships from DB.")
        except Exception as error:
            print(f"Error loading relationships: {error}")

    def add_parameter(self, param: Parameter):
        self.parameters.append(param)
        self._param_map[param.name] = param

    def add_relationship(self, relationship: ParameterRelationship):
        self.relationships.append(relationship)

    def get_parameters(self) -> List[Parameter]:
        return self.parameters

    def __iter__(self):
        return iter(self.parameters)

    def _check_relationship(self, rel: ParameterRelationship, src_val: Any, target_val: Any) -> bool:
        """
        Checks if a single relationship is satisfied.
        Returns True if satisfied, False otherwise.
        """
        if rel.type == "implication":
            # src=true => target=true
            if src_val is True and target_val is not True:
                return False

        elif rel.type == "neg_implication":
            # src=true => target=false
            if src_val is True and target_val is not False:
                return False

        elif rel.type == "weak_implication":
            # src=true => target=true
            if src_val is True and target_val is not True:
                return False

        elif rel.type == "weak_value_implication":
            # src=true => target=target_value
            if src_val is True and target_val != rel.target_value:
                return False

        elif rel.type == "neg_neg_implication":
            # src=false => target=false
            if src_val is False and target_val is not False:
                return False

        elif rel.type == "neg_value_implication":
            # src=false => target=target_value
            if src_val is False and target_val != rel.target_value:
                return False

        elif rel.type == "disable_flag_implication":
            # src=true => target=false
            if src_val is True and target_val is not False:
                return False

        elif rel.type == "value_implication":
            # src=true => target=target_value
            if src_val is True and target_val != rel.target_value:
                return False
        
        return True

    def validate_config(self, config: dict) -> bool:
        """
        Checks if the configuration satisfies all parameter relationships.
        Returns True if valid, False otherwise.
        """
        for rel in self.relationships:
            src_val = config.get(rel.src)
            target_val = config.get(rel.target)

            # Skip if source or target parameter is not in config (assuming partial config is allowed, 
            # or treat missing as default? For now, let's assume we check what's present)
            # Actually, for strict validation, we might need defaults. 
            # But usually config generation starts with defaults.
            if rel.src in config and rel.target in config:
                src_val = config[rel.src]
                target_val = config[rel.target]
                
                if not self._check_relationship(rel, src_val, target_val):
                    return False
        
        return True

    # 暂时先这么做，如果参数存在作为src的依赖关系，则先不尝试对它做修改
    def check_src_dependencies(self, src_param_name: str) -> bool:
        """
        Checks if setting src_param_name to src_value violates any dependencies where it is the source.
        Returns True if valid (no violation), False otherwise.
        """
        relevant_rels = [r for r in self.relationships if r.src == src_param_name]
        
        if relevant_rels is not None:
            return False
        
        return True

    def check_target_dependencies(self, target_param_name: str, target_value: Any, current_config: dict[str, Any]) -> bool:
        """
        Checks if setting target_param_name to target_value violates any dependencies where it is the target.
        If the source parameter is not in current_config, it tries to use the default value.
        Returns True if valid (no violation), False otherwise.
        """
        relevant_rels = [r for r in self.relationships if r.target == target_param_name]
        
        for rel in relevant_rels:
            # Get source value
            src_val = current_config.get(rel.src)
            if src_val is None:
                # Fallback to default
                src_param = self._param_map.get(rel.src)
                if src_param:
                    src_val = src_param.default
                else:
                    # Source parameter unknown or not in our space.
                    # If we can't determine source value, we can't strictly validate.
                    # Assuming valid to avoid blocking potentially valid configs.
                    return False
            
            if not self._check_relationship(rel, src_val, target_value):
                return False
                
        return True
