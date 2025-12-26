from typing import List, Any, Optional

class Parameter:
    """
    Represents a single configuration parameter.
    """
    def __init__(self, name: str, type: str, default: Any, min: Optional[int] = None, max: Optional[int] = None):
        self.name = name
        self.type = type
        self.default = default
        self.min = min
        self.max = max

    def is_bool(self):
        return self.type == "bool"

    def is_int(self):
        return self.type == "int"

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
                
        return []

class ParameterSpace:
    """
    Represents a collection of parameters.
    """
    def __init__(self, parameters: List[Parameter] = None):
        self.parameters = parameters if parameters else []

    def add_parameter(self, param: Parameter):
        self.parameters.append(param)

    def get_parameters(self) -> List[Parameter]:
        return self.parameters

    def __iter__(self):
        return iter(self.parameters)
