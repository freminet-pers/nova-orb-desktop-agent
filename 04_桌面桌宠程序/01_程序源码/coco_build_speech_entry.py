from coco.transcribe_worker import main


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import json
        print(json.dumps({"error": type(exc).__name__}), flush=True)
        raise SystemExit(1)
