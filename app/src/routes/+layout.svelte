<script lang="ts">
  import '$lib/styles/tokens.css';
  import { mode } from '$lib/mode.svelte';

  let { children } = $props();

  $effect(() => mode.init());
</script>

<svelte:head><title>corpora</title></svelte:head>
{@render children()}
