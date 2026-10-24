"""Start the local trace viewer."""

import argparse

from viewer.server import make_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only local agent trace viewer")
    parser.add_argument("--reports", default="reports")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with make_server(args.reports, args.port) as server:
        print(f"http://127.0.0.1:{server.server_port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
