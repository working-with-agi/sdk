import { NgModule } from '@angular/core'
import { CommonModule } from '@angular/common'
import { WorkWithAIComponent } from './work-with-ai.component'
import { UsageMeterComponent } from './usage-meter.component'

@NgModule({
  declarations: [WorkWithAIComponent, UsageMeterComponent],
  imports: [CommonModule],
  exports: [WorkWithAIComponent, UsageMeterComponent],
})
export class WorkWithAIModule {}
