const fs = require('fs');
const glob = require('glob');

const files = glob.sync('src/pages/**/*.tsx');

files.forEach(file => {
  let content = fs.readFileSync(file, 'utf8');

  // Fix verbatimModuleSyntax for react FormEvent
  content = content.replace(/import \{.*?FormEvent.*?\} from 'react';/g, "import { useState } from 'react';\nimport type { FormEvent } from 'react';");
  
  // Fix type-only imports for types
  content = content.replace(/import \{ (.*?Response.*?) \} from '..\/..\/types';/g, "import type { $1 } from '../../types';");
  content = content.replace(/import \{ (.*?Request.*?) \} from '..\/..\/types';/g, "import type { $1 } from '../../types';");

  // Fix missing imports from ui.tsx
  content = content.replace(/, TextField/g, "");
  content = content.replace(/, Select/g, "");
  content = content.replace(/, Banner/g, "");
  content = content.replace(/, ConfirmDialog/g, "");
  content = content.replace(/, TextArea/g, "");
  content = content.replace(/import \{ Card, EmptyState, ErrorState, PageHeader, Skeleton \} from '..\/..\/components\/ui';/, 
    "import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from '../../components/ui';\nimport { TextField } from '../../components/TextField';\nimport { Select } from '../../components/Select';\nimport { Banner } from '../../components/Banner';\nimport { ConfirmDialog } from '../../components/ConfirmDialog';\nimport { TextArea } from '../../components/TextArea';");

  // Fix missing body in EmptyState
  content = content.replace(/<EmptyState title="No career paths found" \/>/g, '<EmptyState title="No career paths found" body="Create a career path to get started." />');

  // Fix missing StatusBadge
  content = content.replace(/<StatusBadge status=\{profile\.data\.statusName === 'Active' \? 'strong' : 'weak'\} \/>/g, '<span className={`badge badge--${profile.data.statusName === "Active" ? "strong" : "weak"}`}></span>');
  content = content.replace(/import \{ dayName, DAY_NAMES/g, 'import { DAY_NAMES');

  // Fix implicit any for 'e'
  content = content.replace(/onChange=\{e =>/g, "onChange={(e: any) =>");

  // Fix implicit any for 'prev' and 'a' in ExpertSessionsPage
  content = content.replace(/prev => prev\?\.map\(a =>/g, "(prev: AppointmentResponse[] | null | undefined) => prev?.map((a: AppointmentResponse) =>");

  fs.writeFileSync(file, content);
});

console.log('Fixed files');
