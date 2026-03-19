import "@xterm/xterm/css/xterm.css";
import "@working-with-agi/vue/style.css";
import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";

const app = createApp(App);
app.use(createPinia());
app.mount("#app");
