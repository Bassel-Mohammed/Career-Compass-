package com.careercompass.mapper;

import com.careercompass.dto.response.CareerPathResponse;
import com.careercompass.entity.CareerPath;
import org.mapstruct.Mapper;

/**
 * `studyFields` (Set&lt;StudyField&gt; -> List&lt;StudyFieldResponse&gt;) is mapped
 * automatically by MapStruct via the sibling {@link StudyFieldMapper}, since both mappers
 * share the same `componentModel = "spring"` and MapStruct composes them at compile time.
 */
@Mapper(componentModel = "spring", uses = StudyFieldMapper.class)
public interface CareerPathMapper {
    CareerPathResponse toResponse(CareerPath careerPath);
}
