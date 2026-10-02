QR_REFRESH = 15
TOTAL_TIMEOUT = 45


async def loop(events):
    user = None
    elapsed = 0.0
    refreshes = 0
    while elapsed < TOTAL_TIMEOUT and user is None:
        event = events.pop(0) if events else "timeout"
        if event == "timeout":
            elapsed += QR_REFRESH
            refreshes += 1
        elif event == "password":
            user = "scanned-with-2fa"
        else:
            user = "scanned"
    return user, refreshes, elapsed


async def main():

    user, refreshes, elapsed = await loop(["timeout"] * 10)
    assert user is None, user
    assert refreshes == 3, refreshes
    assert elapsed == 45, elapsed


    user, refreshes, _ = await loop(["timeout", "scan"])
    assert user == "scanned", user
    assert refreshes == 1, refreshes


    user, _, _ = await loop(["timeout", "password"])
    assert user == "scanned-with-2fa", user

    print("refresh-loop contract OK")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
