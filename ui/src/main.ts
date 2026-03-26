// External
import { createApp } from 'vue'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import Aura from '@primevue/themes/aura'
import 'primeicons/primeicons.css'

// Ours
import App from './App.vue'
import './style.css'

const app = createApp(App)

app.use(ToastService)
app.use(PrimeVue, {
    theme: {
        preset: Aura,
        options: {
            darkModeSelector: false,
            cssLayer: false,
        }
    }
})

app.mount('#app')
