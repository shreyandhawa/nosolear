"""Print the OpenAPI schema as deterministic JSON. Touches no database."""

import json

from nosolear.api.app import create_app


def main() -> None:
    print(json.dumps(create_app().openapi(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
