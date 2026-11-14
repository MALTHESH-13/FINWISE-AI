import asyncio

async def main():
    print("Async running!")
    return 42

if __name__ == "__main__":
    res = asyncio.run(main())
    print("Result:", res)
