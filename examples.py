"""One-click example snippets used by the Streamlit sidebar."""

EXAMPLES: dict[str, str] = {
    "Undefined variable (typo)": '''def calc_total(items):
    total = 0
    for i in range(len(item)):
        total += items[i]
    return total

print(calc_total([10, 20, 30]))
''',

    "Missing import": '''def area_of_circle(radius):
    return math.pi * radius ** 2

def shuffle_and_pick(options):
    random.shuffle(options)
    return options[0]

print(area_of_circle(4))
print(shuffle_and_pick(["a", "b", "c"]))
''',

    "Missing colon (syntax error)": '''def greet(name)
    if name == ""
        return "Hello, stranger!"
    return f"Hello, {name}!"

print(greet("FixMate"))
''',

    "Multiple bugs at once": '''import json

def load_config(path):
    with open(path) as f
        data = json.load(f)
    return dat

def get_timeout(config):
    return config.get("timeout", 30) + random.randint(0, 5)

print(get_timeout({"timeout": 10}))
''',
}
