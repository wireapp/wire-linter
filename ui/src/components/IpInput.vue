<template>
    <div class="ip-input-wrapper">
        <FloatLabel>
            <InputGroup>
                <InputText
                    :id="input_id"
                    :modelValue="modelValue"
                    @update:modelValue="$emit('update:modelValue', $event ?? '')"
                    :placeholder="placeholder"
                    :invalid="invalid"
                    fluid
                />
                <Button
                    icon="pi pi-th-large"
                    severity="secondary"
                    outlined
                    @click="toggle_popover"
                    :aria-label="`Open numpad for ${label}`"
                />
            </InputGroup>
            <label :for="input_id">{{ label }}</label>
        </FloatLabel>

        <Popover ref="popover_ref">
            <div class="ip-numpad">
                <div class="numpad-quickfill">
                    <button
                        v-for="prefix in quick_prefixes"
                        :key="prefix"
                        class="quickfill-btn"
                        @click="apply_prefix(prefix)"
                    >
                        {{ prefix }}
                    </button>
                </div>

                <div class="numpad-grid">
                    <button v-for="key in numpad_keys" :key="key" class="numpad-btn" @click="press_key(key)">
                        <i v-if="key === 'backspace'" class="pi pi-delete-left"></i>
                        <span v-else>{{ key }}</span>
                    </button>
                </div>

                <button class="numpad-clear" @click="clear_input">
                    <i class="pi pi-trash"></i>
                    Clear
                </button>
            </div>
        </Popover>
    </div>
</template>

<script setup lang="ts">
// External
import { ref, useId } from 'vue'
import InputText from 'primevue/inputtext'
import InputGroup from 'primevue/inputgroup'
import Button from 'primevue/button'
import FloatLabel from 'primevue/floatlabel'
import Popover from 'primevue/popover'

// -- Props & Emits --

const props = defineProps<{
    modelValue: string
    label: string
    placeholder?: string
    inputId?: string
    // When true, the inner InputText shows its invalid (red border) state
    invalid?: boolean
}>()

const emit = defineEmits<{
    'update:modelValue': [value: string]
}>()

// stable id for the input
const input_id = props.inputId || useId()

// -- Popover --

const popover_ref = ref()

function toggle_popover(event: Event) {
    popover_ref.value.toggle(event)
}

// -- Numpad --

const quick_prefixes = ['10.0.0.', '192.168.', '172.16.', '127.0.0.']
const numpad_keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'backspace', '0', '.']

function press_key(key: string) {
    if (key === 'backspace') {
        emit('update:modelValue', props.modelValue.slice(0, -1))
    } else {
        emit('update:modelValue', props.modelValue + key)
    }
}

function apply_prefix(prefix: string) {
    emit('update:modelValue', prefix)
}

function clear_input() {
    emit('update:modelValue', '')
}
</script>

<style scoped>
.ip-input-wrapper {
    position: relative;
}

/* numpad inside the popover */
.ip-numpad {
    width: 240px;
    padding: 8px;
}

/* quick-fill row */
.numpad-quickfill {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px;
    margin-bottom: 8px;
}

.quickfill-btn {
    padding: 6px 4px;
    font-size: 12px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    background: var(--wire-light-gray);
    border: 1px solid var(--wire-border-gray);
    border-radius: 4px;
    cursor: pointer;
    color: var(--wire-dark-gray);
    transition: background 0.15s;
}

.quickfill-btn:hover {
    background: var(--wire-blue);
    color: white;
    border-color: var(--wire-blue);
}

/* 3-column grid */
.numpad-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 4px;
    margin-bottom: 8px;
}

.numpad-btn {
    padding: 10px;
    font-size: 16px;
    font-weight: 500;
    background: var(--wire-white);
    border: 1px solid var(--wire-border-gray);
    border-radius: 6px;
    cursor: pointer;
    color: var(--wire-dark-gray);
    transition: background 0.15s;
    display: flex;
    align-items: center;
    justify-content: center;
}

.numpad-btn:hover {
    background: var(--wire-light-gray);
}

.numpad-btn:active {
    background: var(--wire-blue);
    color: white;
    border-color: var(--wire-blue);
}

/* full-width clear button */
.numpad-clear {
    width: 100%;
    padding: 8px;
    font-size: 13px;
    background: var(--wire-light-gray);
    border: 1px solid var(--wire-border-gray);
    border-radius: 4px;
    cursor: pointer;
    color: var(--wire-medium-gray);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    transition: background 0.15s;
}

.numpad-clear:hover {
    background: #ffebe9;
    color: var(--wire-red);
    border-color: var(--wire-red);
}
</style>
