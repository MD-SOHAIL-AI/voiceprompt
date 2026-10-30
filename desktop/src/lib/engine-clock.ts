/** Reject replies from replaced engines and snapshots older than accepted events. */
export class EngineClock {
  generation = 0;
  sequence = 0;
  private updates = new Map<string, number>();
  accept(generation: number, sequence?: number, event?: string) {
    if (generation < this.generation) return false;
    if (generation > this.generation) {
      this.generation = generation;
      this.sequence = 0;
      this.updates.clear();
    }
    if (sequence !== undefined) {
      if (sequence <= this.sequence) return false;
      this.sequence = sequence;
      if (event) this.updates.set(event, sequence);
    }
    return true;
  }
  newerThan(event: string, snapshotSequence: number) {
    return (this.updates.get(event) ?? 0) > snapshotSequence;
  }
}
