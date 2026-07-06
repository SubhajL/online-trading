'use client'

import { AppShell } from '@/components/shell'
import { PageHeader } from '@/components/common/PageHeader'
import { IntegrationPill } from '@/components/common/IntegrationPill'
import { RouterSoakPanel } from '@/components/soak/RouterSoakPanel'
import { useSoak } from '@/hooks/useSoak'

export default function SoakPage() {
  const { status, loading, error } = useSoak()

  return (
    <AppShell>
      <div className="flex flex-col gap-8">
        <PageHeader
          title="Router Soak"
          actions={<IntegrationPill transport="REST" endpoint="/soak/status" />}
        />
        <div className="max-w-xl">
          <RouterSoakPanel status={status} loading={loading} error={error ?? undefined} />
        </div>
      </div>
    </AppShell>
  )
}
