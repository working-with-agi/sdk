import { NgModule } from '@angular/core'
import { CommonModule } from '@angular/common'
import { FormsModule } from '@angular/forms'
import { WorkWithAIComponent } from './work-with-ai.component'

@NgModule({
  declarations: [WorkWithAIComponent],
  imports: [CommonModule, FormsModule],
  exports: [WorkWithAIComponent],
})
export class WorkWithAIModule {}
