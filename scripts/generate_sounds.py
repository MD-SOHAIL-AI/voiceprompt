"""Generate VoicePrompt's original, quiet notification assets using only the stdlib."""
from array import array
import math
from pathlib import Path
import sys
import wave


RATE = 44100


def note(frequency, duration, volume=0.065):
    samples = []
    for index in range(round(RATE * duration)):
        t = index / RATE
        fade_in = min(1, t / 0.012)
        fade_out = min(1, (duration - t) / 0.025)
        envelope = math.sin(fade_in * math.pi / 2) ** 2 * math.sin(fade_out * math.pi / 2) ** 2
        samples.append(round(32767 * volume * envelope * math.exp(-t * 3) * math.sin(2 * math.pi * frequency * t)))
    return samples


def main():
    directory = Path(__file__).resolve().parents[1] / "voiceprompt" / "assets"
    cues = {"start": note(660, 0.09), "stop": note(440, 0.10),
            "reminder": note(523.25, 0.18, 0.08) + [0] * round(RATE * 0.07) + note(659.25, 0.25, 0.08)}
    for name, samples in cues.items():
        pcm = array("h", samples)
        if sys.byteorder != "little":
            pcm.byteswap()
        with wave.open(str(directory / f"{name}.wav"), "wb") as output:
            output.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
            output.writeframes(pcm.tobytes())


if __name__ == "__main__":
    main()
