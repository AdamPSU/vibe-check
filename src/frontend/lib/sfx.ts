type SfxKind = "move" | "click";

let audioContext: AudioContext | null = null;

function getContext() {
  if (typeof window === "undefined") return null;

  const AudioCtx =
    window.AudioContext ||
    (window as typeof window & { webkitAudioContext?: typeof AudioContext })
      .webkitAudioContext;

  if (!AudioCtx) return null;

  if (!audioContext) {
    audioContext = new AudioCtx();
  }

  return audioContext;
}

async function resumeContext(ctx: AudioContext) {
  if (ctx.state === "suspended") {
    await ctx.resume();
  }
}

function tone(
  ctx: AudioContext,
  {
    frequency,
    duration,
    type = "square",
    gain = 0.08,
    slideTo,
    startAt = 0,
  }: {
    frequency: number;
    duration: number;
    type?: OscillatorType;
    gain?: number;
    slideTo?: number;
    startAt?: number;
  },
) {
  const now = ctx.currentTime + startAt;
  const oscillator = ctx.createOscillator();
  const amp = ctx.createGain();

  oscillator.type = type;
  oscillator.frequency.setValueAtTime(frequency, now);
  if (slideTo != null) {
    oscillator.frequency.exponentialRampToValueAtTime(
      Math.max(slideTo, 1),
      now + duration,
    );
  }

  amp.gain.setValueAtTime(0.0001, now);
  amp.gain.exponentialRampToValueAtTime(gain, now + 0.01);
  amp.gain.exponentialRampToValueAtTime(0.0001, now + duration);

  oscillator.connect(amp);
  amp.connect(ctx.destination);
  oscillator.start(now);
  oscillator.stop(now + duration + 0.02);
}

export function playSfx(kind: SfxKind) {
  const ctx = getContext();
  if (!ctx) return;

  void resumeContext(ctx).then(() => {
    if (kind === "move") {
      tone(ctx, {
        frequency: 520,
        slideTo: 780,
        duration: 0.055,
        type: "square",
        gain: 0.055,
      });
      return;
    }

    tone(ctx, {
      frequency: 220,
      duration: 0.05,
      type: "square",
      gain: 0.07,
    });
    tone(ctx, {
      frequency: 440,
      duration: 0.08,
      type: "square",
      gain: 0.06,
      startAt: 0.04,
    });
    tone(ctx, {
      frequency: 660,
      duration: 0.1,
      type: "triangle",
      gain: 0.045,
      startAt: 0.09,
    });
  });
}
