import "zone.js";
import "@angular/compiler";
import "@xterm/xterm/css/xterm.css";
import { bootstrapApplication } from "@angular/platform-browser";
import { AppComponent } from "./app.component";

bootstrapApplication(AppComponent).catch((err) => console.error(err));
