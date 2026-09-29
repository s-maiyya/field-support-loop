"""End-to-end pipeline. Phase 3: STT + extraction only (corroboration/scoring stubbed)."""
import sys
import time
import uuid

from .extract import extract_signal
from .models import Alert
from .stt import transcribe


def run(audio_path: str) -> Alert:
    t0 = time.time()
    timings = {}

    t = time.time()
    transcript = transcribe(audio_path)
    timings["transcribe"] = round(time.time() - t, 2)
    print(f"[pipeline] transcribe {timings['transcribe']}s")

    t = time.time()
    signal = extract_signal(transcript)
    timings["extract"] = round(time.time() - t, 2)
    print(f"[pipeline] extract {timings['extract']}s")

    # TODO Phase 4: corroborate -> score -> playbook -> brief
    alert = Alert(
        alert_id=uuid.uuid4().hex[:8],
        transcript=transcript,
        signal=signal,
        latency_seconds=round(time.time() - t0, 2),
        step_timings=timings,
    )
    return alert


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python -m clear.pipeline <audio_path>")
    a = run(sys.argv[1])
    print("\nTRANSCRIPT:", a.transcript)
    print("\nSIGNAL:")
    print(a.signal.model_dump_json(indent=2))
    print(f"\nlatency: {a.latency_seconds}s  {a.step_timings}")
