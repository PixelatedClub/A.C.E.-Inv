// Deploy only into a university-approved resource group and network.
param location string = resourceGroup().location
param appName string
param approvedLinuxAppServicePlanId string
param integrationSubnetId string
param containerImage string
param tenantId string
param apiClientId string
param desktopClientId string
param sqlServerFqdn string
param sqlDatabase string

resource app 'Microsoft.Web/sites@2023-12-01' = {
  name: appName
  location: location
  kind: 'app,linux,container'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: approvedLinuxAppServicePlanId
    httpsOnly: true
    virtualNetworkSubnetId: integrationSubnetId
    siteConfig: {
      linuxFxVersion: 'DOCKER|${containerImage}'
      minTlsVersion: '1.2'
      scmMinTlsVersion: '1.2'
      ftpsState: 'Disabled'
      alwaysOn: true
      acrUseManagedIdentityCreds: true
      vnetRouteAllEnabled: true
      healthCheckPath: '/health'
      appSettings: [
        { name: 'WEBSITES_PORT', value: '8000' }
        { name: 'ACE_TENANT_ID', value: tenantId }
        { name: 'ACE_API_CLIENT_ID', value: apiClientId }
        { name: 'ACE_DESKTOP_CLIENT_ID', value: desktopClientId }
        { name: 'ACE_SQL_ODBC', value: 'Driver={ODBC Driver 18 for SQL Server};Server=tcp:${sqlServerFqdn},1433;Database=${sqlDatabase};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=15;' }
      ]
    }
  }
}
output apiUrl string = 'https://${app.properties.defaultHostName}'
output managedIdentityObjectId string = app.identity.principalId
