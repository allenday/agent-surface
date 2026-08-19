"""Run the persistent bookstore surface as a native MCP stdio server."""

import asyncio

from examples.bookstore import build_surface, configured_db_path


async def serve() -> None:
    await build_surface(configured_db_path()).mcp().run_stdio()


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
