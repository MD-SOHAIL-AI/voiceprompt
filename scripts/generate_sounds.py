"""Generate VoicePrompt's original, quiet notification assets using only the stdlib."""
from array import array
import math
import random
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


def soft_click(frequency, duration, seed):
    """A rounded, dry tactile click, with a quiet body rather than a beep."""
    generator = random.Random(seed)
    filtered = 0.0
    result = []
    for index in range(round(RATE * duration)):
        t = index / RATE
        filtered += .16 * (generator.uniform(-1, 1) - filtered)
        attack = min(1.0, t / .004)
        fade = min(1.0, (duration - t) / .018)
        envelope = attack * attack * fade * fade * math.exp(-t * 75)
        body = .7 * math.sin(2 * math.pi * frequency * t) + .16 * math.sin(2 * math.pi * frequency * 1.5 * t)
        result.append(round(32767 * .075 * envelope * (body + filtered * .3)))
    return result


def main():
    directory = Path(__file__).resolve().parents[1] / "voiceprompt" / "assets"
    cues = {"start": soft_click(880, 0.060, 11), "stop": soft_click(620, 0.080, 23),
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
