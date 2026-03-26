// use_analysis.ts parses JSONL, runs checkers, and manages results state
// loads sample data on startup so the report tab always has something to show
// takes a ref to the ReportStep component and feeds it results as they come in
//
// Main export is use_analysis({ report_step_ref }) which returns:
//   results: the checker outputs for display
//   data_points_list: the raw parsed data points
//   analyze_data(raw_text, callback): takes JSONL, runs checks, navigates to report

// External
import { ref, nextTick, onMounted } from 'vue'
import type { Ref } from 'vue'
import { useToast } from 'primevue/usetoast'

// Ours
import { sample_jsonl, parse_jsonl } from '../sample-data'
import type { DataPoint, GatheringConfig } from '../sample-data'
import type { CheckOutput } from '../checkers/base_checker'
import { run_checks } from '../checkers/registry'

// ReportStep's exposed API we need this interface because importing the .vue file
// directly causes TypeScript to freak out in plain .ts files
interface ReportStepExposed {
    expand_all(): void
}

// Just needs the report step ref so we can expand trees after loading new data
interface UseAnalysisOptions {
    report_step_ref: Ref<ReportStepExposed | null>
}

// Takes JSONL input, runs all the checkers, populates results, and
// navigates to the report tab so the user can see what we found
export function use_analysis({ report_step_ref }: UseAnalysisOptions) {
    const toast = useToast()

    // checker results, raw data points, and the gathering config from the JSONL header
    const results            = ref<CheckOutput[]>([])
    const data_points_list   = ref<DataPoint[]>([])
    const gathering_config   = ref<GatheringConfig | null>(null)

    // Parses JSONL, runs checkers, stores results, and jumps to the report tab
    function analyze_data(raw_text: string, activateCallback: (step: string) => void): void {
        try {
            // parse it separates the config header from data lines
            const parsed               = parse_jsonl(raw_text)
            gathering_config.value     = parsed.config
            results.value              = run_checks(parsed.data_points, parsed.config)
            data_points_list.value     = parsed.data_points

            // jump to report tab and expand the trees after it renders
            activateCallback('6')
            nextTick(() => report_step_ref.value?.expand_all())
        } catch (error) {
            // tell the user what went wrong instead of silently sitting on step 5
            toast.add({
                severity: 'error',
                summary:  'Failed to analyse results',
                detail:   error instanceof Error ? error.message : String(error),
                life:     8000,
            })
        }
    }

    // load sample data when the component mounts so the report tab never feels empty
    onMounted(() => {
        try {
            const parsed               = parse_jsonl(sample_jsonl)
            gathering_config.value     = parsed.config
            results.value              = run_checks(parsed.data_points, parsed.config)
            data_points_list.value     = parsed.data_points

            // expand the trees once they've rendered
            nextTick(() => report_step_ref.value?.expand_all())
        } catch (error) {
            // don't crash if a checker explodes, just log it and keep going
            console.error('Sample data preload failed:', error)
        }
    })

    return { results, data_points_list, gathering_config, analyze_data }
}
