/**
 * Ignore the answer to a question you have stopped asking.
 *
 * Reported from the running app: "search does it once; once the content is
 * cleared and the user tries to search again, it doesn't filter anymore."
 *
 * The cause is not the filter. It is that `/api/sources` takes **0.48s with no
 * search and 1.2–5.8s with one** — a search reads every file in the corpus,
 * an unsearched page reads only the fifty it shows. So clearing the box issues a
 * fast request while a slow one is still in flight, and whichever lands LAST
 * wins. Arrival order has nothing to do with typing order, and the list ends up
 * showing the results of a query the operator has already moved on from.
 *
 * Debouncing does not fix this. It reduces how many requests are issued; it
 * cannot order the ones that are.
 *
 * The fix is a monotonic token: every request takes a number, and a response
 * whose number is not the newest is dropped. Kept here rather than inline in the
 * component because the rule is worth testing and a component is not.
 */
export class Latest {
  #issued = 0;

  /** Claim the next slot. Call once, at the start of a request. */
  next(): number {
    return ++this.#issued;
  }

  /** Whether `token` is still the most recent claim. */
  current(token: number): boolean {
    return token === this.#issued;
  }

  /**
   * Run `work`, resolving to its value only if no newer call has started.
   * Returns `undefined` for a superseded call, which the caller ignores.
   *
   * A rejection is NOT swallowed — a stale failure is dropped, but a current one
   * still throws, because an error the operator is waiting on must surface.
   */
  async run<T>(work: () => Promise<T>): Promise<T | undefined> {
    const token = this.next();
    try {
      const value = await work();
      return this.current(token) ? value : undefined;
    } catch (err) {
      if (this.current(token)) throw err;
      return undefined;
    }
  }
}
