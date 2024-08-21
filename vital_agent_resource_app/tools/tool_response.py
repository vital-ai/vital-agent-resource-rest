
class ToolResponse:
    def __init__(self, data: dict):
        self.data = data

    def to_dict(self):
        return self.data


