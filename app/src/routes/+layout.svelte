<script lang="ts">
  let { children } = $props();
</script>

<svelte:head><title>corpora</title></svelte:head>
{@render children()}

<style>
  :global(:root) {
    color-scheme: light dark;
    --bg: #fbfbfa; --panel: #fff; --ink: #1b1b19; --dim: #6b6b66;
    --line: #e4e4e0; --accent: #2f6f5e; --warn: #b23c17; --chip: #eef1ef;
    --shadow: 0 1px 2px rgba(0,0,0,.05), 0 4px 12px rgba(0,0,0,.04);
  }
  @media (prefers-color-scheme: dark) {
    :global(:root) {
      --bg: #141513; --panel: #1c1e1b; --ink: #e9e9e4; --dim: #9a9a92;
      --line: #2b2e2a; --accent: #6fd0ac; --warn: #ff8a5c; --chip: #242723;
      --shadow: none;
    }
  }
  :global(*) { box-sizing: border-box; }
  :global(body) {
    margin: 0; background: var(--bg); color: var(--ink);
    font: 14.5px/1.55 ui-sans-serif, -apple-system, "Segoe UI", Inter, system-ui, sans-serif;
  }
</style>
