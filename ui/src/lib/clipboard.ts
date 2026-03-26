// clipboard.ts: Vue composable for copying text with a brief "copied!" indicator
//
// use_clipboard() gives you a { copy, is_copied } handle. Each call gets its own
// independent state, so you can have multiple copy buttons on the same page without
// them interfering with each other. call copy(text) to copy, and is_copied lights up
// for a couple seconds to show it worked.

// External
import { ref, onScopeDispose, type Ref } from 'vue'

// Duration in milliseconds to hold is_copied=true after a successful copy
const COPIED_DURATION = 2000

export interface ClipboardHandle {
    // calls navigator.clipboard to copy text, then briefly shows the feedback state
    copy:      (text: string) => Promise<void>
    // lights up for a couple seconds after a copy succeeds
    is_copied: Ref<boolean>
}

export function use_clipboard(): ClipboardHandle {
    const is_copied = ref(false)
    // if user clicks rapidly, we cancel the old timer and start fresh so the
    // feedback always shows for the full duration from the last click
    let timer_id: ReturnType<typeof setTimeout> | null = null

    async function copy(text: string): Promise<void> {
        try {
            await navigator.clipboard.writeText(text)
            is_copied.value = true
            if (timer_id !== null) clearTimeout(timer_id)
            timer_id = setTimeout(() => { is_copied.value = false; timer_id = null }, COPIED_DURATION)
        } catch {
            // clipboard might not be available in older browsers or non-HTTPS, just warn and move on
            console.warn('Clipboard API not available')
        }
    }

    // clear any pending timer when the composable's effect scope is disposed (component unmount)
    onScopeDispose(() => { if (timer_id !== null) clearTimeout(timer_id) })

    return { copy, is_copied }
}
