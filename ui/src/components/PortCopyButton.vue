<template>
    <button class="copy-btn" @click="copy(command)">
        <i class="pi" :class="is_copied ? 'pi-check' : 'pi-copy'"></i>
    </button>
</template>

<script setup lang="ts">
// Ours
import { use_clipboard } from '../lib/clipboard'

// -- Props --

defineProps<{
    // text to copy when clicked
    command: string
}>()

// each instance has its own clipboard handle so is_copied state doesn't bleed
const { copy, is_copied } = use_clipboard()
</script>

<style scoped>
/* flush to the right edge of the command box */
.copy-btn {
    padding: 8px 12px;
    background: #2a2a4e;
    color: #94a3b8;
    border: none;
    border-radius: 0 6px 6px 0;
    cursor: pointer;
    transition: all 0.15s;
}

.copy-btn:hover {
    background: #3a3a5e;
    color: white;
}
</style>
