class Side:
    instances = []

    def __init__(self, name):
        self.name = name
        if len(self.instances) >= 2:
            raise ValueError("You shouldn't be doing this")
        self.instances.append(self)

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self.name == other.name

    def __ne__(self, other):
        return not (self == other)

    def __repr__(self):
        return self.name

    def get_opposite(self):
        for instance in self.instances:
            if instance == self:
                continue
            return instance


ASK = Side('ASK')
BID = Side('BID')
