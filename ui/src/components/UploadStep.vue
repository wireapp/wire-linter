<!--
    UploadStep.vue: Step 5 of the fact gathering wizard.

    Accepts multiple JSONL result files. Shows a checklist of what's been
    uploaded and what's still needed (based on Step 2 config). Displays
    metadata cards for each uploaded file.

    Emits:
      - 'back': step back to step 4
      - 'analyze': send the array of raw JSONL entries for analysis
-->
<template>
    <div class="step-content">
        <h1 class="step-title">Upload Results</h1>
        <p class="step-description">
            Upload the JSONL result files from each runner invocation. You can upload
            multiple files (backend, DMZ calling, client probes from different networks).
        </p>

        <!-- Upload checklist -->
        <div class="upload-checklist">
            <h3 class="checklist-title">Upload Checklist</h3>
            <div class="checklist-item" :class="{ done: has_backend_main }">
                <i :class="has_backend_main ? 'pi pi-check-circle' : 'pi pi-circle'"></i>
                <span>Backend results (main cluster)</span>
                <span class="checklist-badge required">required</span>
            </div>
            <div v-if="setup.calling_in_dmz" class="checklist-item" :class="{ done: has_backend_calling }">
                <i :class="has_backend_calling ? 'pi pi-check-circle' : 'pi pi-circle'"></i>
                <span>Backend results (calling DMZ cluster)</span>
                <span class="checklist-badge required">required</span>
            </div>
            <div class="checklist-item" :class="{ done: has_client }">
                <i :class="has_client ? 'pi pi-check-circle' : 'pi pi-circle'"></i>
                <span>Client reachability results</span>
                <span class="checklist-badge recommended">recommended</span>
            </div>
        </div>

        <!-- Uploaded files list -->
        <div v-if="uploaded_files.length > 0" class="uploaded-files">
            <div v-for="(file, index) in uploaded_files" :key="index" class="file-card">
                <button class="file-card-remove" @click="remove_file(index)" title="Remove file">
                    <i class="pi pi-times"></i>
                </button>
                <div class="file-card-name">{{ file.filename }}</div>
                <div class="file-card-meta">
                    <span v-if="file.source_type"><strong>Type:</strong> {{ file.source_type }}</span>
                    <span v-if="file.gathered_from"><strong>Source:</strong> {{ file.gathered_from }}</span>
                    <span v-if="file.network_name"><strong>Network:</strong> {{ file.network_name }}</span>
                    <span v-if="file.cluster_type && file.cluster_type !== 'both'"><strong>Cluster:</strong> {{ file.cluster_type }}</span>
                    <span v-if="file.domain"><strong>Domain:</strong> {{ file.domain }}</span>
                    <span><strong>Data points:</strong> {{ file.data_point_count }}</span>
                </div>
            </div>
        </div>

        <!-- Upload area -->
        <div class="upload-section">
            <div class="upload-tabs">
                <button class="upload-tab" :class="{ active: upload_mode === 'file' }" @click="upload_mode = 'file'">
                    <i class="pi pi-upload"></i>
                    Upload File
                </button>
                <button class="upload-tab" :class="{ active: upload_mode === 'paste' }" @click="upload_mode = 'paste'">
                    <i class="pi pi-file-edit"></i>
                    Paste Data
                </button>
            </div>

            <div v-if="upload_mode === 'paste'" class="paste-area">
                <Textarea
                    v-model="paste_input"
                    placeholder='Paste JSONL data here, then click "Add"...'
                    :rows="10"
                    fluid
                    style="font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 12px;"
                />
                <Button label="Add Pasted Data" icon="pi pi-plus" size="small" severity="secondary"
                    style="margin-top: 8px;" @click="add_pasted_data" :disabled="!paste_input.trim()" />
            </div>

            <div v-if="upload_mode === 'file'" class="file-area">
                <FileUpload
                    mode="basic"
                    accept=".jsonl,.json,.txt"
                    choose-label="Choose JSONL File"
                    @select="handle_file_upload"
                    :auto="false"
                />
                <p v-if="upload_error" class="file-error">
                    <i class="pi pi-exclamation-triangle"></i>
                    {{ upload_error }}
                </p>
            </div>

            <div class="sample-data-hint">
                <Button label="Use Sample Data" severity="secondary" size="small" outlined @click="load_sample_data" />
                <span class="hint-text">Load example data to preview the report</span>
            </div>
        </div>

        <div class="step-actions">
            <Button label="Back" severity="secondary" icon="pi pi-arrow-left" @click="emit('back')" />
            <Button label="Analyze" icon="pi pi-check" icon-pos="right"
                @click="emit('analyze', uploaded_files.map(f => f.raw_text).join('\n'))"
                :disabled="!has_backend_main" />
        </div>
    </div>
</template>

<script setup lang="ts">
// External
import { ref, computed } from 'vue'
import Textarea from 'primevue/textarea'
import Button from 'primevue/button'
import FileUpload from 'primevue/fileupload'

// Ours
import type { SetupData } from '../lib/settings_yaml'
import { sample_jsonl, parse_jsonl } from '../sample-data'

// An uploaded result file with parsed metadata for display
interface UploadedFile {
    filename:         string
    raw_text:         string
    source_type:      string
    gathered_from:    string
    network_name:     string
    cluster_type:     string
    domain:           string
    data_point_count: number
}

const { setup } = defineProps<{
    setup: SetupData
}>()

const emit = defineEmits<{
    back: []
    // For backward compatibility, still emits a single string.
    // The parent (App.vue) receives this and can split/parse as needed.
    // In the future this could emit the UploadedFile array directly.
    analyze: [raw_text: string]
}>()

// State
const upload_mode    = ref<'paste' | 'file'>('file')
const paste_input    = ref('')
const upload_error   = ref('')
const uploaded_files = ref<UploadedFile[]>([])

// Checklist computed properties
const has_backend_main = computed((): boolean => {
    return uploaded_files.value.some(f =>
        f.source_type === 'backend' && (f.cluster_type === 'both' || f.cluster_type === 'main')
    )
})

const has_backend_calling = computed((): boolean => {
    return uploaded_files.value.some(f =>
        f.source_type === 'backend' && f.cluster_type === 'calling'
    )
})

const has_client = computed((): boolean => {
    return uploaded_files.value.some(f => f.source_type === 'client')
})

// Parse JSONL text and extract metadata for display
function parse_file_metadata(raw_text: string, filename: string): UploadedFile {
    const parsed = parse_jsonl(raw_text)
    const config = parsed.config

    return {
        filename,
        raw_text,
        source_type:      config?.source_type ?? (config?.gathered_from === 'client' ? 'client' : 'backend'),
        gathered_from:    config?.gathered_from ?? 'unknown',
        network_name:     config?.network_name ?? '',
        cluster_type:     config?.cluster_type ?? 'both',
        domain:           config?.cluster?.domain ?? '',
        data_point_count: parsed.data_points.length,
    }
}

// Handle file upload
function handle_file_upload(event: { files?: File[] }) {
    const file = event.files?.[0]
    if (!file) return

    upload_error.value = ''

    const reader = new FileReader()
    reader.onload = (e) => {
        const text: string = (e.target?.result as string) || ''
        try {
            const entry: UploadedFile = parse_file_metadata(text, file.name)
            uploaded_files.value = [...uploaded_files.value, entry]
        } catch (err) {
            upload_error.value = `Failed to parse "${file.name}": ${err instanceof Error ? err.message : String(err)}`
        }
    }
    reader.onerror = () => {
        upload_error.value = `Couldn't read "${file.name}".`
    }
    reader.readAsText(file)
}

// Handle pasted data
function add_pasted_data() {
    const text: string = paste_input.value.trim()
    if (!text) return

    try {
        const count: number = uploaded_files.value.length + 1
        const entry: UploadedFile = parse_file_metadata(text, `pasted-data-${count}.jsonl`)
        uploaded_files.value = [...uploaded_files.value, entry]
        paste_input.value = ''
    } catch (err) {
        upload_error.value = `Failed to parse pasted data: ${err instanceof Error ? err.message : String(err)}`
    }
}

// Remove a file from the list
function remove_file(index: number) {
    uploaded_files.value = uploaded_files.value.filter((_, i) => i !== index)
}

// Load sample data
function load_sample_data() {
    try {
        const entry: UploadedFile = parse_file_metadata(sample_jsonl, 'sample-data.jsonl')
        uploaded_files.value = [entry]
    } catch {
        // Fallback: just set it as the only file
        uploaded_files.value = [{
            filename: 'sample-data.jsonl',
            raw_text: sample_jsonl,
            source_type: 'backend',
            gathered_from: 'admin-host',
            network_name: 'sample',
            cluster_type: 'both',
            domain: 'example.com',
            data_point_count: 0,
        }]
    }
}
</script>

<style scoped>
.step-content {
    animation: fade-in 0.3s ease;
}

@keyframes fade-in {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}

.step-title {
    font-size: 28px;
    font-weight: 700;
    color: var(--wire-black);
    margin-bottom: 8px;
}

.step-description {
    font-size: 15px;
    color: var(--wire-medium-gray);
    margin-bottom: 24px;
    line-height: 1.6;
}

/* Upload checklist */
.upload-checklist {
    border: 1px solid var(--wire-border-gray);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 20px;
    background: var(--wire-white);
}

.checklist-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--wire-dark-gray);
    margin-bottom: 10px;
}

.checklist-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    font-size: 13px;
    color: var(--wire-medium-gray);
}

.checklist-item.done {
    color: var(--wire-dark-gray);
}

.checklist-item.done i {
    color: #22c55e;
}

.checklist-badge {
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 4px;
    font-weight: 500;
    margin-left: auto;
}

.checklist-badge.required {
    background: #fef2f2;
    color: #dc2626;
}

.checklist-badge.recommended {
    background: #fffbeb;
    color: #d97706;
}

/* Uploaded files cards */
.uploaded-files {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 20px;
}

.file-card {
    position: relative;
    border: 1px solid var(--wire-border-gray);
    border-radius: 8px;
    padding: 12px 16px;
    background: var(--wire-white);
}

.file-card-remove {
    position: absolute;
    top: 8px;
    right: 8px;
    width: 24px;
    height: 24px;
    border: none;
    background: none;
    color: var(--wire-medium-gray);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
}

.file-card-remove:hover {
    background: #fef2f2;
    color: #dc2626;
}

.file-card-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--wire-dark-gray);
    margin-bottom: 6px;
}

.file-card-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    font-size: 12px;
    color: var(--wire-medium-gray);
}

.file-card-meta strong {
    color: var(--wire-dark-gray);
    font-weight: 500;
}

/* Upload section */
.upload-section {
    margin-top: 8px;
}

.upload-tabs {
    display: flex;
    gap: 0;
    margin-bottom: 16px;
    border: 1px solid var(--wire-border-gray);
    border-radius: 8px;
    overflow: hidden;
    width: fit-content;
}

.upload-tab {
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    border: none;
    background: var(--wire-white);
    color: var(--wire-medium-gray);
    display: flex;
    align-items: center;
    gap: 8px;
    transition: all 0.2s;
}

.upload-tab:not(:last-child) {
    border-right: 1px solid var(--wire-border-gray);
}

.upload-tab.active {
    background: var(--wire-blue);
    color: white;
}

.upload-tab:not(.active):hover {
    background: var(--wire-light-gray);
}

.paste-area {
    margin-bottom: 16px;
}

.file-area {
    padding: 32px;
    border: 2px dashed var(--wire-border-gray);
    border-radius: 8px;
    text-align: center;
    margin-bottom: 16px;
}

.file-error {
    margin-top: 12px;
    font-size: 13px;
    color: var(--p-red-500, #ef4444);
    display: flex;
    align-items: center;
    gap: 6px;
    justify-content: center;
}

.sample-data-hint {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 16px;
}

.hint-text {
    font-size: 13px;
    color: var(--wire-medium-gray);
}

.step-actions {
    display: flex;
    justify-content: space-between;
    margin-top: 32px;
}
</style>
