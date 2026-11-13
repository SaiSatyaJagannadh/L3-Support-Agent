// Skeleton of the spec's Azure resources (private endpoints/VNet/WAF/APIM omitted: add per landing zone). Deploy: az deployment group create -f main.bicep
param location string = resourceGroup().location
param prefix string = 'l3agent'
resource openai 'Microsoft.CognitiveServices/accounts@2024-10-01' = { name: '${prefix}-oai', location: location, kind: 'OpenAI', sku: { name: 'S0' }, properties: { publicNetworkAccess: 'Disabled', customSubDomainName: '${prefix}-oai' } }
resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = { name: '${prefix}-search', location: location, sku: { name: 'standard' }, properties: { publicNetworkAccess: 'disabled', semanticSearch: 'standard' } }
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = { name: '${prefix}-kv', location: location, properties: { tenantId: subscription().tenantId, sku: { family: 'A', name: 'standard' }, enableRbacAuthorization: true, publicNetworkAccess: 'Disabled' } }
resource sqlsrv 'Microsoft.Sql/servers@2023-08-01-preview' = { name: '${prefix}-sql', location: location, properties: { publicNetworkAccess: 'Disabled', minimalTlsVersion: '1.2' } }
resource sqldb 'Microsoft.Sql/servers/databases@2023-08-01-preview' = { parent: sqlsrv, name: 'l3agent', location: location, sku: { name: 'S1' } }
resource apim 'Microsoft.ApiManagement/service@2023-09-01-preview' = { name: '${prefix}-apim', location: location, sku: { name: 'Developer', capacity: 1 }, properties: { publisherEmail: 'admin@example.com', publisherName: 'L3 Agent' } }
