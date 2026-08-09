<script lang="ts">
  import '$lib/styles/tokens.css';

  let { children } = $props();
</script>

<svelte:head><title>corpora</title></svelte:head>
{@render children()}
