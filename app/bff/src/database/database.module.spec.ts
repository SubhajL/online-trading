import { TypeOrmModule } from '@nestjs/typeorm';
import { DatabaseModule } from './database.module';
import { DatabaseSchemaVerifierService } from './database-schema-verifier.service';

describe('DatabaseModule', () => {
  it('should be defined', () => {
    expect(DatabaseModule).toBeDefined();
  });

  it('imports TypeOrmModule', () => {
    const imports = Reflect.getMetadata('imports', DatabaseModule) || [];
    const hasTypeOrmModule = imports.some((importedModule: any) => {
      return importedModule === TypeOrmModule || importedModule?.module === TypeOrmModule;
    });

    expect(hasTypeOrmModule).toBe(true);
  });

  it('registers DatabaseSchemaVerifierService', () => {
    const providers = Reflect.getMetadata('providers', DatabaseModule) || [];

    expect(providers).toContain(DatabaseSchemaVerifierService);
  });
});
