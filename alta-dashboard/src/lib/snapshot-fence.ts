/** Prevent late reads from replacing a newer read or an acknowledged write. */
export class SnapshotFence {
  private revision = 0;

  begin() {
    return ++this.revision;
  }

  accepts(revision: number) {
    return revision === this.revision;
  }

  invalidate() {
    this.revision++;
  }
}
