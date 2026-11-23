"""The 5 concepts from the assignment, plus the key terms my own check looks for."""

CONCEPTS = [
    {
        "id": 1,
        "concept": "Pythagoras' theorem",
        "subject": "Maths",
        "text": "In a right-angled triangle, the longest side is called the hypotenuse. "
                "The square of the hypotenuse is equal to the sum of the squares of the "
                "other two sides: a² + b² = c².",
        "key_terms": ["hypotenuse", "a", "b", "c"],
    },
    {
        "id": 2,
        "concept": "Parts of a circle",
        "subject": "Maths",
        "text": "A circle has a centre. The radius is the distance from the centre to the edge. "
                "The diameter goes across the circle through the centre and is twice the radius. "
                "The circumference is the distance around the circle.",
        "key_terms": ["centre", "radius", "diameter", "circumference"],
    },
    {
        "id": 3,
        "concept": "Series circuit",
        "subject": "Physics",
        "text": "In a series circuit there is only one loop. The current is the same everywhere "
                "in the loop. The voltage of the cell is shared between the components.",
        "key_terms": ["cell", "current", "voltage"],
    },
    {
        "id": 4,
        "concept": "Photosynthesis",
        "subject": "Biology",
        "text": "Plants take in carbon dioxide and water. They use light energy, absorbed by "
                "chlorophyll, to make glucose and oxygen.",
        "key_terms": ["carbon dioxide", "water", "light", "chlorophyll", "glucose", "oxygen"],
    },
    {
        "id": 5,
        "concept": "States of matter",
        "subject": "Chemistry",
        "text": "In a solid the particles are close together and vibrate in place. In a liquid "
                "they are close but move past each other. In a gas they are far apart and move fast.",
        "key_terms": ["solid", "liquid", "gas"],
    },
]


def get_concept(concept_id: int) -> dict:
    for c in CONCEPTS:
        if c["id"] == concept_id:
            return c
    raise KeyError(f"No concept with id {concept_id}")
