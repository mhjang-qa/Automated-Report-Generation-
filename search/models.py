from dataclasses import dataclass, field, asdict

FIELD_WEIGHTS = {'title': 1.0, 'screen': .9, 'actual': .9, 'steps': .7,
                 'expected': .5, 'body': .45, 'comments': .25}


@dataclass
class Defect:
    id: str
    title: str
    notion_url: str
    screen: str = ''
    actual: str = ''
    steps: str = ''
    expected: str = ''
    body: str = ''
    comments: str = ''
    severity: str = ''
    priority: str = ''
    status: str = ''
    target_version: str = ''
    platform: str = ''
    environment: str = ''
    created_at: str = ''
    updated_at: str = ''
    assignee: str = ''
    property_mapping: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)
