<!-- SummaryCards.vue - Row of status-count cards summarizing check results.

     Extracted from CheckResultsTree to separate display from tree rendering.

     Shows Total, Healthy, Warnings, Unhealthy, plus conditional Not Tested card.
     Derives all counts from the flat CheckOutput[] array.

     Props: results (CheckOutput[] for computing counts)
-->
<template>
    <div class="summary-cards">
        <div class="summary-card total">
            <div class="count">{{ results.length }}</div>
            <div class="label">Total Checks</div>
        </div>
        <div class="summary-card healthy">
            <div class="count">{{ healthy_count }}</div>
            <div class="label">Healthy</div>
        </div>
        <div class="summary-card warning">
            <div class="count">{{ warning_count }}</div>
            <div class="label">Warnings</div>
        </div>
        <div class="summary-card unhealthy">
            <div class="count">{{ unhealthy_count }}</div>
            <div class="label">Unhealthy</div>
        </div>
        <div v-if="gather_failure_count > 0" class="summary-card gather-failure">
            <div class="count">{{ gather_failure_count }}</div>
            <div class="label">Gather Failures</div>
        </div>
        <div v-if="not_applicable_count > 0" class="summary-card not-applicable">
            <div class="count">{{ not_applicable_count }}</div>
            <div class="label">Not Tested</div>
        </div>
    </div>
</template>

<script setup lang="ts">
// External
import { computed } from 'vue'

// Ours
import type { CheckOutput } from '../checkers/base_checker'

// -- Props --

const props = defineProps<{
    results: CheckOutput[]
}>()

// -- Computed summary counts (single-pass reduce over the results array) --

const status_counts = computed(() => {
    const counts = { healthy: 0, warning: 0, unhealthy: 0, gather_failure: 0, not_applicable: 0 }
    for (const r of props.results) {
        if (r.status in counts) {
            counts[r.status as keyof typeof counts]++
        }
    }
    return counts
})

const healthy_count        = computed(() => status_counts.value.healthy)
const warning_count        = computed(() => status_counts.value.warning)
const unhealthy_count      = computed(() => status_counts.value.unhealthy)
const gather_failure_count = computed(() => status_counts.value.gather_failure)
const not_applicable_count = computed(() => status_counts.value.not_applicable)

defineExpose({ healthy_count, warning_count, unhealthy_count, gather_failure_count, not_applicable_count })
</script>

<style scoped>
/* horizontal row of status-count cards */
.summary-cards {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
}

.summary-card {
    flex: 1;
    min-width: 140px;
    padding: 20px;
    border-radius: 8px;
    text-align: center;
    border: 1px solid var(--wire-border-gray);
}

.summary-card .count {
    font-size: 32px;
    font-weight: 700;
    line-height: 1.2;
}

.summary-card .label {
    font-size: 13px;
    color: var(--wire-medium-gray);
    margin-top: 4px;
}

/* status-specific count colors */
.summary-card.total          .count { color: var(--wire-blue); }
.summary-card.healthy        .count { color: var(--wire-green); }
.summary-card.unhealthy      .count { color: var(--wire-red); }
.summary-card.warning        .count { color: var(--wire-orange); }
.summary-card.gather-failure .count { color: var(--wire-orange); }
.summary-card.not-applicable .count { color: #757575; }

/* collapse to vertical stack on narrow viewports */
@media (max-width: 768px) {
    .summary-cards {
        flex-direction: column;
    }

    .summary-card {
        min-width: unset;
    }
}
</style>
